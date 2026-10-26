# Isolated Sandbox API

## Routes And Boundaries

The main FastAPI application mounts a separate application at `/sandbox`.
Both applications include the same routers and use the same validation,
application services, gateways, and transaction implementations. Only their
dependency configuration differs; no request changes global environment values,
production connections, or production service singletons.

| Existing Route | Sandbox Route |
|---|---|
| `/auth/login` | `/sandbox/auth/login` |
| `/auth/logout` | `/sandbox/auth/logout` |
| `/customers` | `/sandbox/customers` |
| `/orders` | `/sandbox/orders` |
| `/products` and `/products/{id}` | `/sandbox/products` and `/sandbox/products/{id}` |
| `/integrations/salesforce/events` | `/sandbox/integrations/salesforce/events` |
| `/health` | `/sandbox/health` |

Swagger: <http://127.0.0.1:8000/sandbox/docs>. The child OpenAPI schema is at
`/sandbox/openapi.json`; its paths are relative to its own server URL. The main
OpenAPI schema remains separate. The mount inherits the existing ASGI proxy
`root_path`: for example `/public-api/sandbox/docs` and
`/public-api/sandbox/openapi.json`. No Caddy change is required by this code;
the proxy must already forward the application's existing prefix correctly.

The sandbox always uses the PostgreSQL synchronization adapter, regardless of
the existing application's `CUSTOMER_SYNC_BACKEND` setting. Its database is
`life365_sandbox`, owned by `sandbox_user`. The automated-test role cannot
connect to that database. Existing routes and crons retain their original
database configuration and can still access real services; `/sandbox` is not
a global safety switch for the project.

## Configuration

For native execution, add these settings to the project's untracked `.env`, or
export them in the process environment. Environment values take priority over
`.env`. Do not change the production `DATABASE_URL` or production secrets.

```dotenv
SANDBOX_DATABASE_HOST=127.0.0.1
SANDBOX_DATABASE_PORT=55432
SANDBOX_DB_PASSWORD=sandbox_local_only
SANDBOX_JWT_SECRET_KEY=<independent random secret, at least 32 bytes>
SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET=<another independent random secret, at least 32 bytes>
```

Generate two independent values, for example by running `openssl rand -hex 32`
twice. Do not store actual secrets in tracked files or commit `.env`. Neither
sandbox secret may equal either production secret, and the two sandbox secrets
must differ. Keep the fingerprint secret stable while keeping event history:
changing it prevents matching fingerprints for previous events. Changing the
JWT secret invalidates sandbox tokens.

| Setting | Meaning |
|---|---|
| `SANDBOX_DATABASE_HOST` | Native `127.0.0.1`, `localhost`, or `::1`; Docker `local-postgres` |
| `SANDBOX_DATABASE_PORT` | Native `55432`; Docker `5432` |
| `SANDBOX_DB_PASSWORD` | Password for the local `sandbox_user` role; must match database initialization |
| `SANDBOX_JWT_SECRET_KEY` | Independent sandbox JWT signing key |
| `SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET` | Independent HMAC key for sandbox event fingerprints |

The database name and role are fixed in configuration code. There is no sandbox
`DATABASE_URL` fallback or option to select the production database. Other
host/port combinations are rejected. Sandbox configuration is loaded once when
the application is constructed; restart the API after changing it.

`make run`, `make docker-dev-up`, and `make docker-prod-up` already start and
wait for the shared `postgres:18.6` container. Both Compose API services override
the sandbox host/port to `local-postgres:5432` on `local-database`, and pass the
local password plus the two sandbox secrets. Secrets can come from `.env` or
shell exports. No production DSN or scheduler setting is replaced.

If sandbox settings are missing or invalid, startup logs a configuration warning
without secret values. Sandbox data/auth operations return `503` with no fallback;
its docs remain available. Existing endpoint behavior is not changed. If the
local database is unavailable, sandbox persistence operations return `503`.

## Authentication

Only locally initialized sample accounts authenticate in this environment:

| Username | Password | `principal_type` | Role |
|---|---|---|---|
| `sandbox-admin` | `sandbox-admin` | `user` | admin |
| `sandbox-buyer` | `sandbox-buyer` | `user` | buyer |
| `salesforce` | `romi` | `user` | admin |
| `sandbox-customer-1` through `sandbox-customer-7` | `sandbox-customer` | `customer` | customer |

These are deliberately public local-only sample passwords, not production
credentials. Do not expose the sample environment to untrusted users.
Customer listing and synchronization remain admin-only. Other role and product
scope rules are unchanged.

From the repository root (requires `curl`, `jq`, and Python 3):

```bash
BASE_URL=http://127.0.0.1:8000/sandbox
AUTH_TOKEN=$(curl --fail-with-body -sS "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{"username":"sandbox-admin","password":"sandbox-admin","principal_type":"user"}' \
  | jq -er '.access_token')

curl --fail-with-body -sS "$BASE_URL/customers?limit=10&offset=0" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

For a deployed reverse-proxy prefix, set `BASE_URL` to that prefix followed by
`/sandbox`, not the existing application's root. Sandbox JWTs include the issuer
`life365-sandbox` and audience `life365-public-api:sandbox`. Existing tokens fail
on sandbox endpoints and sandbox tokens fail on existing endpoints (`401`).

Sandbox token sessions are held in a separate **in-memory store per application
process**, never the production SQLite file. Use **one API worker**, as in the
current Dockerfile; multiple workers or replicas need a shared sandbox-only
session adapter before use. Reload/restart loses sessions, so log in again.
Logout revokes only the current sandbox session:

```bash
curl --fail-with-body -sS -X POST "$BASE_URL/auth/logout" \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

## Create A Customer

Use the full canonical fixture, changing only synthetic demo identities. The
fixture supplies all required sections; the agent metadata is replaced with
the local sample agent. Run from the repository root after authenticating.

```bash
umask 077
CREATE_FILE=$(mktemp /tmp/life365-sandbox-create.XXXXXX.json)
UPDATE_FILE=$(mktemp /tmp/life365-sandbox-update.XXXXXX.json)

jq --arg event_id "$(python3 -c 'import uuid; print(uuid.uuid4())')" \
  --arg login "sandbox-demo-$(date +%s)" \
  '.eventId = $event_id
   | .data.credentials.login = $login
   | .data.primaryContact.email = ($login + "@example.com")
   | .data.commercial.assignedAgent = {
       referenceId: 117, userLogin: "sandbox-agent-117", name: "Sample Agent 117",
       email: "agent-117@example.com", phone: null
     }' \
  tests/fixtures/integrations/salesforce/customer-created-v1.json > "$CREATE_FILE"

CREATE_RESULT=$(curl --fail-with-body -sS "$BASE_URL/integrations/salesforce/events" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H 'Content-Type: application/json' --data-binary "@$CREATE_FILE")
printf '%s\n' "$CREATE_RESULT" | jq
REFERENCE_ID=$(printf '%s\n' "$CREATE_RESULT" | jq -er '.referenceId')
```

A successful committed operation returns
`{"success":true,"eventId":"<same UUID>","referenceId":<generated local ID>}`.
Create must not supply `referenceId`; update must supply it. Both use
`schemaVersion: 1`; `resourceVersion` is rejected with `422`.

## Partial Update

```bash
jq -n --arg event_id "$(python3 -c 'import uuid; print(uuid.uuid4())')" \
  --arg occurred_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson reference_id "$REFERENCE_ID" \
  '{schemaVersion: 1, eventId: $event_id, occurredAt: $occurred_at,
    eventType: "customer.updated", referenceId: $reference_id,
    data: {company: {website: null, primaryPhone: ""},
           commercial: {paymentDays: 0, preferredCategories: []},
           extensions: {parameters: {sandboxDemo: true}}}}' > "$UPDATE_FILE"

curl --fail-with-body -sS "$BASE_URL/integrations/salesforce/events" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H 'Content-Type: application/json' --data-binary "@$UPDATE_FILE" | jq
```

Omitted fields and siblings remain unchanged. Permitted `null` values clear
fields. Supplied arrays replace the whole array, including `[]` to clear it.
JSON extensions merge recursively, retaining unrelated keys; nested null removes
a key, while null for an entire nullable extension clears it. Required-field
clearing and unknown references are still rejected. The canonical
[contract](integrations/SALESFORCE_CUSTOMER_EVENTS_V1.md) remains authoritative.

Send events **one at a time per customer**, waiting for a successful response.
After a timeout or uncertain result, resend the saved file with the same
`eventId` and identical content before continuing. Do not regenerate its ID or
timestamp during a retry. Different customers may be synchronized concurrently.
`occurredAt` is metadata, not an ordering mechanism.

Completed replay returns the original result without mutation. Reusing an ID
with changed content returns `409`; missing customers return `404`; malformed
payloads or invalid data return `422`; persistence failures return `503`.
Customer changes and event completion commit together. Failed operations roll
back. Advisory event locking prevents concurrent duplicates and customer row
locking protects partial updates and JSON merges. Event logs contain secure
HMAC fingerprints and results, not raw payloads or passwords.

Keep the two temporary request files until the operations have a known outcome,
then remove them:

```bash
rm -- "$CREATE_FILE" "$UPDATE_FILE"
unset AUTH_TOKEN
```

## External Integrations And Temporary Data

`GET /sandbox/products/recommend?order_id=1` (or `customer_id=1`) still validates
authentication and arguments, but returns **501 Not Implemented**. Its injected
adapter sends no external HTTP request; it does not pretend a recommendation
succeeded. Incoming Salesforce events write only local PostgreSQL; they do not
send outbound Salesforce requests. New future external gateways must also receive
sandbox-safe adapters before being exposed here.

The shared PostgreSQL container uses tmpfs. Stopping it loses **both** databases;
the next start reloads the bundled sandbox sample and initializes an empty test
database. Local customers, event history, and replay protection are lost.
Do not replay historical events assuming their history survived the reset.
Restart the API and log in again after a database reseed: otherwise process-local
sessions might still reference remapped/reused local IDs. Restarting the API
alone does not erase PostgreSQL data or event history.

The sandbox schema is a subset, not a production replica: it supports the exposed
reads and customer synchronization, but excludes unrelated workflows and
production triggers/extensions. See [local PostgreSQL](LOCAL_POSTGRESQL.md).
No seed/migration changes were necessary: initialization already applies both
synchronization migrations to the sandbox.

## Verification

```bash
make test-postgresql
CUSTOMER_SYNC_BACKEND=memory DATABASE_URL=postgresql://localhost/test \
  .venv/bin/pytest -q
```

The first command uses only `life365_public_api_test_customer_sync` and includes
the sandbox HTTP test module. That module checks the actual connection name and
requires an empty test database before loading the bundled sandbox schema/seed,
then removes only its test tables. **Never** point destructive fixtures at the
seeded sandbox or production. Unit tests use fake credentials and no real business
HTTP calls. Coverage includes configuration, proxy-aware Swagger, JWT/session
isolation, admin authorization, explicit database selection, seeded reads, full
create, partial update, replay/restart, conflicts, rollback, concurrent duplicate
delivery, JSON merges, and blocked external calls.

### Implementation Verification (2026-10-26)

- `make test-postgresql`: **46 passed, 2 skipped**. The skips are intentionally
  PostgreSQL-specific cases in the parameterized in-memory backend, not failed
  PostgreSQL checks.
- Full suite with `CUSTOMER_SYNC_BACKEND=memory`, dummy main
  `DATABASE_URL=postgresql://localhost/test`, and the dedicated local
  `CUSTOMER_SYNC_TEST_DATABASE_URL`: **1190 passed, 2 skipped**.
- Ruff import sorting, formatting, and configured lint checks passed for all
  changed Python files; `git diff --check` passed.
- Rendered Compose configuration verified both API services' sandbox environment,
  shared private network, and healthy-PostgreSQL dependency without printing
  secret values. A disposable PostgreSQL client container verified read-only
  `local-postgres` DNS/connectivity as `sandbox_user`, the event schema, 7 sample
  customers, and an empty event log. No running database was restarted.
- A temporary native Uvicorn server verified real localhost HTTP: sandbox
  Swagger/OpenAPI, health, seeded admin login, 7 customers, cross-environment
  `401`, recommendations `501`, logout, and revoked-token `401`. It was stopped
  afterward. This check did not write customer/event rows.

The API image was not rebuilt or deployed during these checks; Docker API
configuration and network connectivity were verified separately. Production
routes were regression-tested with injected dependencies, not against live
production services. Actual `.env` values were not modified. Configure stable
sandbox secrets before enabling the mounted data/auth routes. Neither production
deployment nor reverse-proxy configuration was changed.
