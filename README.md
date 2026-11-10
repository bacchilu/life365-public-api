# Life365 Public API

FastAPI application for Life365 public APIs.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
pip3 freeze > requirements-lock.txt
```

## Run

Create a local `.env` file from the example and set the real database URL:

```bash
cp .env.example .env
```

`.env` is ignored by git.

```bash
fastapi dev app/main.py
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "ok", "db": "ok"}
```

For Salesforce customer event setup, migrations, and request examples, see
[the synchronization runbook](docs/integrations/SALESFORCE_CUSTOMER_SYNC_RUNBOOK.md).

For the opposite direction, integration-only POST/PUT export the complete existing
customer synchronously to Salesforce. Normal and `/sandbox` routes both make
real calls to its configured UAT API; only the source database differs. See
[the customer export guide](docs/integrations/SALESFORCE_CUSTOMER_EXPORT.md).

Inspect the SQLite token sessions:

```bash
sqlite3 -header -column data/token-sessions.sqlite3 \
  'SELECT * FROM token_sessions;'
```

Example output:

```text
token_id                              principal_id  principal_type  issued_at                         expires_at                        revoked
------------------------------------  ------------  --------------  --------------------------------  --------------------------------  -------
388331e6-aa53-4e9e-a0a7-2c63de38c2a3  2             user            2026-07-29T12:12:02.239790+00:00  2026-08-28T12:12:02.239790+00:00  0
6b14e691-3ec1-4649-9174-12e1bc67f79d  2             user            2026-07-29T12:12:06.377408+00:00  2026-08-28T12:12:06.377408+00:00  0
```

## Authentication Roles

Internal users authenticate through `/auth/login` with `principal_type: "user"`.
Supported internal roles are `admin`, `buyer`, and `integration`; customer
accounts authenticate with `principal_type: "customer"` and receive the
`customer` role. The server reads the role from the database, not the login
request. An internal user with `users.role = 'INTEGRATION'` receives
`"role": "integration"` in the login response and JWT. Existing JWT validation,
session handling, and logout also support this role.

The `integration` role authorizes **all `/integrations` routes**, including
incoming customer events and outgoing customer, product, and order operations.
Only this role is accepted: `admin`, `buyer`, and `customer` receive `403`.
It has no product permissions or product access outside these routes.
`GET /customers` remains admin-only. Endpoints that require
authentication alone retain their existing behavior; for example, `/orders`
does not currently require a specific role.

The versioned `users.role` column is text (`varchar(45)`), so this role does
not require a schema migration. The bundled sandbox account `salesforce` /
`romi` now has the `integration` role; other seeded accounts are unchanged.
For an existing sandbox, apply the guarded role upgrade described in
[the sandbox guide](docs/SANDBOX_API.md#upgrade-an-existing-sandbox-account)
without restarting PostgreSQL or loading the seed again. Normal production
accounts are not changed automatically. Existing tokens are not revoked;
log in again to obtain the account's current role. An old admin token cannot
authorize integration operations.

## Customer Synchronization To Salesforce

These **integration-only** endpoints send a customer that already exists in Life365
to Salesforce:

| Method and route | Event sent | Successful API response |
|---|---|---|
| `POST /integrations/salesforce/customers/{customer_id}` | `customer.created` | HTTP 201 |
| `PUT /integrations/salesforce/customers/{customer_id}` | `customer.updated` | HTTP 200 |

`customer_id` is the ID in the selected Life365 database, not a Salesforce
Account ID. Both requests accept **no body**: the API reads the customer and
its related data, builds the complete payload, and waits for Salesforce's
response. They do not create or modify the customer in the Life365 database.

PUT sends the full current customer, not a partial patch. Life365 values take
priority over the shared Salesforce fields, including the documented boolean
normalization rules. Save changes in Life365 before requesting synchronization.

The API server must have `SALESFORCE_TOKEN_URL`, `SALESFORCE_CLIENT_ID`, and
`SALESFORCE_CLIENT_SECRET` configured. It manages Salesforce authentication and
access-token renewal; callers supply only their **Life365 JWT**.

### Authenticate

The following examples use the Life365 sandbox on the production domain and
require `curl` and `jq`. Its bundled `salesforce` / `romi` credentials identify
a sandbox integration account, not a Salesforce OAuth user or a production Life365 account.

```bash
API_URL='https://b2b.life365.eu/public-api/sandbox'

AUTH_TOKEN=$(curl --fail-with-body -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{"username":"salesforce","password":"romi","principal_type":"user"}' \
  | jq -er '.access_token')
```

**Sandbox exports make real calls to the configured Salesforce API**, currently
its UAT sandbox. They read only `life365_sandbox` on the API server. Normal and
sandbox exports share the Salesforce reference namespace, so choose test IDs
carefully: the same numeric ID can target the same remote Account.

### Create The Salesforce Customer

Replace the placeholder with an existing Life365 customer ID that has not yet
been exported to Salesforce. This does not create a new customer in Life365.

```bash
CUSTOMER_ID='<EXISTING_LIFE365_CUSTOMER_ID>'

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/customers/$CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

### Update The Salesforce Customer

For example, synchronize the current data of sandbox customer `3` to its
existing Salesforce representation:

```bash
CUSTOMER_ID=3

curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/customers/$CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Both operations return the same response structure. For the update above:

```json
{
  "success": true,
  "eventId": "<EVENT_UUID>",
  "referenceId": 3,
  "accountId": "<SALESFORCE_ACCOUNT_ID>"
}
```

`referenceId` is the Life365 ID; `accountId` identifies the Salesforce Account.
Each call generates a new `eventId`. Send calls for one customer sequentially.
There is no durable outgoing retry history; after a timeout, check Salesforce
before repeating an uncertain operation. Only an upstream HTTP 401 causes one
automatic token renewal and retransmission of the same event.

For normal production customer data, use
`API_URL='https://b2b.life365.eu/public-api'` and authenticate again with a
production account with the `integration` role. Those routes read the existing `DATABASE_URL`;
sandbox credentials and tokens cannot be reused. For local sandbox testing,
use `API_URL='http://127.0.0.1:8000/sandbox'` instead and authenticate there.

See [the customer export guide](docs/integrations/SALESFORCE_CUSTOMER_EXPORT.md)
for configuration, normalization, and error responses. Interactive documentation
is available for [production](https://b2b.life365.eu/public-api/docs) and
[sandbox](https://b2b.life365.eu/public-api/sandbox/docs).

## Product Synchronization To Salesforce

Integration-only endpoints send an existing Life365 catalog product to Salesforce:

| Method and route | Event | Success |
|---|---|---|
| `POST /integrations/salesforce/products/{product_id}` | `product.created` | HTTP 201 |
| `PUT /integrations/salesforce/products/{product_id}` | `product.updated` | HTTP 200 |
| `DELETE /integrations/salesforce/products/{product_id}` | `product.deleted` | HTTP 200 |

No request body is accepted. The API reads `products.id` (not a stock ID),
resolves its brand/category/image, builds the minimal DTO, and waits for
Salesforce. PUT sends every shared field. DELETE only deactivates Salesforce's
record; no Life365 data is changed. PUT can reactivate it when the local
product has `enabled=true`.

Use the sandbox authentication example above, then:

```bash
PRODUCT_ID=101

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

curl --fail-with-body -sS -X DELETE \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Responses include `success`, `eventId`, `referenceId`, and `recordId` (the
Salesforce Product2 ID). `/sandbox` reads only its local sample database but
makes real Salesforce calls. Normal and sandbox product IDs share one remote
namespace, so the same ID can overwrite the same Salesforce product.

OAuth settings and the in-memory token cache are shared with customer exports.
`SALESFORCE_PRODUCT_SYNC_URL` is optional; it defaults to the token URL's
origin plus `/services/apexrest/product/sync/`. There is no outgoing retry
table; only HTTP 401 triggers one token renewal and identical-event retry.

See [the product export guide](docs/integrations/SALESFORCE_PRODUCT_EXPORT.md)
for EAN/category rules, configuration, errors, full examples, and the additive
schema setup needed by an already initialized sandbox. No production database
migration is required.

## Order Synchronization To Salesforce

Integration-only, body-free routes export an existing `orders.id`:

| Method and route | Event | Success |
|---|---|---|
| `POST /integrations/salesforce/orders/{order_id}` | `order.created` | 201 |
| `PUT /integrations/salesforce/orders/{order_id}` | `order.updated` | 200 |
| `DELETE /integrations/salesforce/orders/{order_id}` | `order.deleted` | 200 |

Synchronize the order's customer first. POST/PUT send the full snapshot and
all lines; DELETE marks only the Salesforce record as deleted. No Life365 order
or outgoing history is written. Both normal and `/sandbox` routes make real
Salesforce calls; the sandbox source remains local PostgreSQL only.

Use the authentication above, then choose an order from `$API_URL/orders`:

```bash
ORDER_ID=1001

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/orders/$ORDER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/orders/$ORDER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

The seeded order `1001` belongs to customer `4`; export that customer before
the order if it is not already synchronized. Amounts use signed line totals,
nonnegative unit prices, an `ADMGST` shipping line, recorded gross and derived
combined tax. Status is the unchanged logistic state. No date/state filter
is imposed by export-by-ID. Optional `SALESFORCE_ORDER_SYNC_URL` defaults to
the token origin plus `/services/apexrest/order/sync/`; OAuth/cache and the
single 401 retry are shared with other exports.

See [the Italian Life365 guide](life365.md#sincronizzazione-degli-ordini) and
[the technical order guide](docs/integrations/SALESFORCE_ORDER_EXPORT.md) for
DELETE, errors, limits, totals, sample setup, and file responsibilities.

## Docker

Build the image with a container user matching the current host user:

```bash
docker build --build-arg USER_ID="$(id -u)" --build-arg GROUP_ID="$(id -g)" -t life365-public-api:latest .
```

Run the source bundled in the image in production mode:

```bash
docker run --rm -it --env-file .env -p 8000:8000 \
  -v "$(pwd)/data:/data" life365-public-api
```

Run in development mode with automatic reload and the repository bind-mounted
at `/app`:

```bash
docker run --rm -it --env-file .env -p 8000:8000 \
  -v "$(pwd):/app" -v "$(pwd)/data:/data" \
  life365-public-api fastapi dev app/main.py \
  --host 0.0.0.0 --port 8000
```

The same modes are available through Docker Compose. Start development mode
with:

```bash
make docker-dev-up
```

Start production mode in the background with:

```bash
make docker-prod-up
```

Stop the corresponding Compose services with:

```bash
make docker-dev-down
make docker-prod-down
```

The production service joins the external `life365-shared` network and exposes
port `8000` only to containers on that network. The production Make target
creates the shared network when it does not already exist.

## Local PostgreSQL

`make run`, `make docker-dev-up`, `make docker-prod-up`, and
`make docker-test-db-up` start and wait for the same `postgres:18.6` service.
An already running database container is reused without restarting it.
Its `unless-stopped` restart policy starts it again when Docker starts after a
host reboot, provided it was not manually stopped. Docker must itself be enabled
at boot. A manually stopped database remains stopped until explicitly started.
Changing Compose does not update an existing container by itself. To apply the
policy without recreating or stopping that container, use
`docker update --restart unless-stopped <POSTGRES_CONTAINER>` on the intended
host. This preserves its currently loaded temporary data.

- `life365_sandbox` starts with a small, sanitized production-derived sample:
  7 customers, 12 orders, 24 order lines, and 24 products (including the local
  `ADMGST` service product) plus reference catalogs.
- `life365_public_api_test_customer_sync` is a separate, initially empty database
  used by `make test-postgresql`. Its user cannot connect to the sandbox, and
  the sandbox user cannot connect to the test database.
- Host connections use `127.0.0.1:55432`; API containers can use
  `local-postgres:5432` on the private `local-database` network.

The application's `DATABASE_URL` and existing API/scheduler behavior are
**unchanged**. Provisioning this database does not redirect any endpoint to it.
There is no refresh command or automatic production export. The sample is loaded
from the versioned files under `docker/postgres/sandbox`, not from production.

Storage is temporary (`tmpfs`, 512 MB maximum by default). **Stopping the
database container loses both databases.** A host reboot also loses them; the
automatic restart does not make tmpfs persistent. Starting it again restores the
bundled sandbox seed and an empty automated-test database. API down commands
leave the database running; `make docker-test-db-down` explicitly stops it and
prints a data-loss warning.

See [the local PostgreSQL guide](docs/LOCAL_POSTGRESQL.md) for credentials,
sample scope, lifecycle, configuration, and verification details.

## Sandbox API

The same routes are available under `/sandbox`, with independent authentication,
sessions, and PostgreSQL dependencies. Swagger is at
`http://127.0.0.1:8000/sandbox/docs` (or the existing proxy prefix followed by
`/sandbox/docs`). Existing routes still use their original configuration.

Configure the explicit sandbox database settings and two separate random secrets
in `.env`, using `.env.example` as a reference, then restart the API. Without
valid sandbox configuration, sandbox operations return `503`; they never fall
back to production. The local admin login is `sandbox-admin` / `sandbox-admin`
with `principal_type: "user"`. These credentials work only on sandbox routes.

See [the sandbox API guide](docs/SANDBOX_API.md) for configuration, authentication,
create/update curl examples, isolation, unsupported external operations, and the
single-worker session limit.

## Existing Authentication Sessions

Authentication sessions are stored in `/data/token-sessions.sqlite3`. Docker
Compose bind-mounts the repository's `data` directory at `/data`; Git tracks
the directory scaffold but ignores the generated SQLite files.

If PostgreSQL runs directly on the Docker host, use
`host.docker.internal` instead of `localhost` in `DATABASE_URL` and add this
option to `docker run` on Linux:

```text
--add-host host.docker.internal:host-gateway
```
