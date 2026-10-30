# Customer Export From Life365 To Salesforce

## Scope And Direction

These admin-only operations notify Salesforce about a customer **already saved
and committed in Life365**:

| Method and route | Outbound event | Successful local response |
|---|---|---|
| `POST /integrations/salesforce/customers/{customer_id}` | `customer.created` | HTTP 201 |
| `PUT /integrations/salesforce/customers/{customer_id}` | `customer.updated` | HTTP 200 |

Neither route accepts a request body. Both read every shared customer section
from PostgreSQL, build a new event, call Salesforce, and wait for its response.
PUT sends the complete current representation, including nulls and empty arrays:
Life365 takes priority for the shared data. This is not a partial PATCH endpoint.
Salesforce remains responsible for its internal Account/Additional_Email mapping;
a positive API response alone does not verify every remote field was persisted.

These routes do not create or change customers in Life365. They do not use the
incoming event table, create new tables, record outbound events, or start workers,
queues, or a retry scheduler. The existing incoming
`POST /integrations/salesforce/events` is unchanged and retains its own transactions
and durable replay handling. Creating an incoming customer does not automatically
send it back to Salesforce; export requires an explicit outbound request.

## Sandbox Behavior

The same routes exist under `/sandbox`. They read **only `life365_sandbox`**;
an ID missing there returns 404 without a remote request or production fallback.
An ID is always local to the selected database, even if the same integer exists
in another environment. Normal routes use the existing `DATABASE_URL`.

**Both environments make real calls to the same configured Salesforce API**,
currently its UAT sandbox. They use the same adapter implementation, credentials,
and process-local token cache. This does not merge the two Life365 databases,
JWT identities, or login sessions. Test IDs in the two databases can collide in
Salesforce because both use the same remote reference namespace: deliberately
choose customers before exporting. A sandbox PUT can overwrite that remote
reference's shared fields.

This outbound customer integration is an explicit exception to the original
external-service restriction. Product recommendations remain disabled with 501
inside `/sandbox`. Automated tests mock Salesforce and do not send real data.

## Configuration

Read from `.env` and the process environment (environment wins), without changing
the active environment during a request:

```dotenv
SALESFORCE_TOKEN_URL=https://java-nosoftware-4269--partial.sandbox.my.salesforce.com/services/oauth2/token
SALESFORCE_CLIENT_ID=<client id supplied privately>
SALESFORCE_CLIENT_SECRET=<client secret supplied privately>
SALESFORCE_CUSTOMER_SYNC_URL=https://java-nosoftware-4269--partial.sandbox.my.salesforce.com/services/apexrest/customer/sync/
SALESFORCE_TIMEOUT_SECONDS=30
```

The customer URL is optional: it defaults to the token URL's origin plus
`/services/apexrest/customer/sync/`. Both URLs must be HTTPS, without embedded
credentials, query parameters, or fragments, and use the same origin. The
timeout must be positive and at most 120 seconds. Configuration errors return
503 without exposing credentials. No secrets are included in committed examples.

The current authentication is **OAuth client credentials**, already used by the
project and verified manually against Salesforce UAT. It is not the JWT Bearer
assertion flow described in the external Postman document. A future change of
destination uses configuration; a change of authentication protocol belongs in
the infrastructure adapter. No new environment values need to be added for a
working installation that already configures the three existing Salesforce keys.

Settings and the adapter are constructed lazily; missing Salesforce settings do
not prevent unrelated API routes from starting. Restart the API after changing
remote settings. The scheduler's existing authentication code is not changed.

## Token And Failure Policy

`app/infrastructure/salesforce/auth.py` keeps the access token in a module-level
variable, keyed to the configured token URL and client credentials. The first
request authenticates; subsequent requests reuse it. An async lock avoids
simultaneous authentication when multiple requests need the first token.
Each API worker has its own cache. Restarting a worker loses its cached token,
which is obtained again when needed. This cache is separate from Life365 JWT
session storage.

There is one explicit exception to the no-retry policy:

1. If the event request receives HTTP 401, invalidate the token that was used.
2. Authenticate again (or use a token another concurrent request just renewed).
3. Repeat **once**, with the identical event ID, timestamp, and JSON payload.
4. If the second request also fails, return an error. A second 401 invalidates
   that token too; there is no third attempt.

Authentication errors, connection failures, timeouts, validation errors,
conflicts, rate limits, and server errors do not cause other automatic retries.
Redirects are not followed. Success requires HTTP 200/201 and a valid JSON result
with `success: true`, matching event/reference IDs, and a nonempty `accountId`.
Salesforce's numeric-string `referenceId` is converted to an application integer.
Remote bodies, access tokens, client secrets, and customer passwords are not
included in application errors or logs.

Every independent POST or PUT generates a new UUID and UTC `occurredAt`.
`referenceId` is the existing Life365 ID **for both create and update**.
`schemaVersion` is 1; `resourceVersion` is never sent. Metadata timestamps do not
implement ordering. Callers must send operations for one customer in sequence.

There is no durable outgoing idempotency guarantee. A repeated client call is
a new operation and reads the latest local values. A delivery timeout or network
failure may mean Salesforce applied the event but its response was lost; the
API does not retry that uncertain outcome. Investigate before issuing another
create. No PostgreSQL/HTTP distributed transaction or rollback is claimed.

## HTTP Responses

| HTTP status | Meaning |
|---|---|
| 201 POST / 200 PUT | Salesforce confirmed the matching operation |
| 401 | Missing or invalid Life365 token |
| 403 | Life365 user is not an admin |
| 404 | Customer missing from the selected local database; no Salesforce call |
| 409 | Salesforce returned a conflict |
| 422 | Invalid ID, nonempty body, or local data cannot form the shared DTO |
| 502 | Remote authentication/delivery/response failed, including remote 400/404/5xx |
| 503 | Local database unavailable or remote configuration missing/invalid |
| 504 | Authentication/delivery timed out; delivery may have an uncertain outcome |

The remote status is not confused with local authentication: an upstream 401
after the one renewal attempt becomes 502, not a request to log into Life365 again.
Logs identify exports by `event_id`, `reference_id`, and event type, without the
customer payload. Responses contain only `success`, `eventId`, `referenceId`,
and `accountId`, never the exported credentials.

## Concrete Requests

The following commands use the **real Salesforce UAT destination**, reading a
customer from the local sandbox. They require valid sandbox configuration and
an API already running (`make run` or `make docker-dev-up`). Use one API worker
for the sandbox's existing in-memory Life365 sessions.

```bash
BASE_URL=http://127.0.0.1:8000/sandbox
AUTH_TOKEN=$(curl --fail-with-body -sS "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{"username":"salesforce","password":"romi","principal_type":"user"}' \
  | jq -er '.access_token')

# Inspect local customers first; the ID is local to life365_sandbox.
curl --fail-with-body -sS "$BASE_URL/customers?limit=10&offset=0" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

CUSTOMER_ID=1
# Creates an Account using referenceId=1; do not run blindly on an existing reference.
curl --fail-with-body -sS -X POST \
  "$BASE_URL/integrations/salesforce/customers/$CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

# Sends ALL shared fields from the current local customer, not a partial patch.
curl --fail-with-body -sS -X PUT \
  "$BASE_URL/integrations/salesforce/customers/$CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

For normal routes remove `/sandbox` and authenticate on the normal login endpoint;
the read then uses the existing `DATABASE_URL`, but the remote destination is the
same. Do not use real customer data unless that transfer is intended.

## Reading And Mapping Rules

The export reader uses one read-only PostgreSQL transaction and one SQL snapshot
for the complete customer, billing/delivery regions and countries, agent, channel,
categories, and shop groups. It closes the database connection **before** HTTP
authentication/delivery. It never writes `last_login_date`, event history, or any
other customer state.

The shared DTO covers credentials, company, primary contact, both addresses,
tax, communication preferences, registration, commercial data, banking, shop,
operational settings, notes, and extensions. Relevant details:

- Credentials are the stored Life365 values. Existing legacy hashes are not
  decoded into original plaintext passwords. Sensitive values are sent only to
  the configured Salesforce API and excluded from representations/logs.
- Decimal columns stay `Decimal` until serialization into exact two-decimal
  strings, without float conversion or rounding. Only coordinates become floats.
- Timestamp-without-zone columns follow the existing synchronization convention:
  UTC wall times are exported with a UTC offset. Verify older data conventions
  before exporting legacy records written by other applications.
- Regions supply `countryCode` and `regionName`. Agent IDs resolve into the full
  descriptive object. A null agent stays null.
- Codes use the same catalogs as incoming synchronization. Category labels prefer
  English, then Italian. Sales-channel labels remove the code prefix; shop labels
  come from their reference rows. Reference order is preserved.
- SQL NULL arrays become empty shared arrays. Null JSON extensions remain null;
  empty objects and unrelated nested keys remain intact.
- Only for outbound Salesforce payloads, nullable booleans use the defaults
  listed below, because their Salesforce checkbox fields do not accept null.
  `normalization.py` applies these rules to a copy of the customer DTO before
  `payload.py` serializes it. Existing `true` and `false` values are preserved,
  including an explicit `prepaidReturns: false`. The database, original
  application DTOs, incoming synchronization, and all other nullable fields
  retain their existing behavior.
- Legacy additional emails and notes are decoded to their full shared shapes.
  Missing required flags are rejected rather than silently assigning consent.
- Missing required strings/regions, unsupported reference IDs, malformed JSON,
  and incomplete delivery addresses produce 422 before any remote request.
  Repair the source data rather than inventing labels, IDs, or required values.
- `registrationIp` and `notes.openCount` are absent from the shared payload.

### Outbound Boolean Defaults

| Payload field | Value sent when the Life365 value is NULL |
|---|---|
| `communicationPreferences.newsletter` | `false` |
| `communicationPreferences.privacyRegistered` | `false` |
| `communicationPreferences.rulesRegistered` | `false` |
| `registration.verified` | `false` |
| `operationalSettings.disableQuantityDelivery` | `false` |
| `operationalSettings.prepaidReturns` | `true` |
| `operationalSettings.disableSaleLimit` | `false` |

These rules apply to both outbound create and update events. They do not change
`taxProfile.viesValidated` or `operationalSettings.disableBoxDiscount`, which
already require non-null booleans.

The canonical [incoming contract](SALESFORCE_CUSTOMER_EVENTS_V1.md) describes
the shared data sections. Its create envelope is deliberately different: inbound
create has no `referenceId`, whereas outbound create must identify the already
existing Life365 customer.

## Verification And Layer Responsibilities

```bash
make test-postgresql
CUSTOMER_SYNC_BACKEND=memory DATABASE_URL=postgresql://localhost/test \
  .venv/bin/pytest -q
```

All automated remote calls use `httpx.MockTransport` or typed fake gateways.
The PostgreSQL fixture checks the exact isolated database
`life365_public_api_test_customer_sync`, requires empty test storage, loads the
bundled seed, and cleans only its own test tables. It never changes production
or the seeded sandbox. No outgoing migration is needed.

Verification on 2026-10-27:

- `make test-postgresql`: 54 passed, 2 intentionally skipped in-memory variants
  of PostgreSQL-only checks.
- Full regression with a dummy main DSN and the dedicated test database:
  1252 passed, 2 skipped.
- Both required commands, `ruff check --select I --fix <file>` and
  `ruff format <file>`, passed separately for every one of the 28 changed Python
  files. The configured Ruff lint checks and `git diff --check` also passed.
- Pyright checked all changed Python files and tests using the project virtual
  environment: 0 errors, 0 warnings. The checker was installed only in `/tmp`;
  project dependencies and lockfiles were not changed.
- A temporary native Uvicorn server verified real localhost HTTP: normal and
  sandbox OpenAPI schemas, unauthenticated 401 responses, local sandbox login,
  customer listing, and missing-customer 404 for both POST and PUT. The existing
  local sandbox contained 8 customers during this check; none was changed.
  The verification server was stopped, without restarting existing containers.

No new live Salesforce export was sent during implementation verification;
remote delivery and token expiry were tested with simulated HTTP responses.
Earlier manual UAT calls in this session independently confirmed the remote
create/update endpoint, but they did not exercise these newly implemented routes.
The API image was not rebuilt or deployed, and actual `.env` values, Caddy,
production databases, and runtime customer data were not changed.

### API Layer

| File | Responsibility and reason |
|---|---|
| `app/api/integrations/exports.py` | Defines POST/PUT, the response schema, body/path rules, Swagger descriptions, and HTTP error translation. It does not access SQL or HTTP clients. |
| `app/api/integrations/export_dependencies.py` | Enforces admin access and composes the normal service with the configured PostgreSQL reader and lazy real Salesforce adapter. |
| `app/api/integrations/__init__.py` | Registers incoming and outgoing routers together so both FastAPI applications reuse them. |
| `app/api/sandbox/services.py` | Composes the export service with the sandbox DSN and the same real remote adapter; other sandbox services remain isolated. |
| `app/api/sandbox/__init__.py` | Overrides only the export service's database composition for the mounted app and updates its external-call description. |

### Application Layer

| File | Responsibility and reason |
|---|---|
| `app/application/dtos/customer_integration/export.py` | Frozen, slotted event/result dataclasses. Both event types carry a local reference and full existing customer DTO; sensitive event data is omitted from repr. |
| `app/application/ports.py` | Adds typed read-only customer-reader and Salesforce-delivery Protocols, keeping concrete libraries outside the use case. |
| `app/application/services/customer_export_service.py` | Validates the operation, loads the customer, generates UUID/UTC metadata, requests one delivery, verifies the matching result, and logs IDs only. No persistence, HTTP, or SQL. |
| `app/application/exceptions.py` | Adds safe configuration, remote-request, and timeout errors that the API can translate without depending on HTTP client exceptions. |

### Infrastructure Layer

| File | Responsibility and reason |
|---|---|
| `app/infrastructure/data_mapper/customer_export/__init__.py` | Implements the reader Protocol with a short read-only transaction and safe database errors. |
| `app/infrastructure/data_mapper/customer_export/query.py` | Retrieves the customer and all needed reference data in one SQL snapshot, preserving reference-array order. |
| `app/infrastructure/data_mapper/customer_export/customer.py` | Maps the complete database row into all nested application DTO sections. |
| `app/infrastructure/data_mapper/customer_export/references.py` | Converts local foreign keys into shared address, agent, category, channel, and shop-group objects. |
| `app/infrastructure/data_mapper/customer_export/values.py` | Parses legacy JSON and UTC timestamps, preserving null/false/empty intent and rejecting unrepresentable required data. |
| `app/infrastructure/data_mapper/customer_sync/reference_codes.py` | Owns shared bidirectional reference-code catalogs, avoiding different mappings for reads and writes. |
| `app/infrastructure/data_mapper/customer_sync/categories.py`, `sales_channels.py`, `shop_groups.py` | Reuse those catalogs; incoming reference resolution retains its previous behavior. |
| `app/infrastructure/salesforce/settings.py` | Loads and validates remote URL/credentials/timeout settings without mutating global environment values. |
| `app/infrastructure/salesforce/auth.py` | Owns module-level token cache, authentication lock, credential scoping, and conditional invalidation. |
| `app/infrastructure/salesforce/normalization.py` | Applies approved defaults to the seven nullable booleans in a copy of the customer DTO, preserving explicit values and all other fields. |
| `app/infrastructure/salesforce/payload.py` | Serializes application dataclasses into camelCase JSON, financial strings, UTC timestamps, and complete arrays while retaining extension keys. |
| `app/infrastructure/salesforce/client.py` | Implements the gateway with real HTTP, one 401 renewal/retransmission, response correlation, and safe errors. |
| `app/infrastructure/salesforce/__init__.py` | Exposes the settings and concrete adapter for composition without leaking HTTP details into the application. |

### Tests And Configuration

| File | Responsibility and reason |
|---|---|
| `tests/test_customer_export_service.py` | Verifies full snapshots, new event identity, missing customers, exception preservation, and no use-case retries. |
| `tests/test_salesforce_customer_api.py` | Verifies exact HTTP payloads, cached/concurrent auth, one 401 retry, no other retries, settings, response validation, and credential-safe errors. |
| `tests/test_customer_export_api.py` | Verifies POST/PUT, admin checks, normal/sandbox reader selection, input rules, error mapping, and OpenAPI. |
| `tests/test_customer_export_postgresql.py` | Verifies seeded/full-round-trip reads, exact values, invalid legacy data, authenticated exports through the real adapter with mocked HTTP, and unchanged customer/event tables. |
| `scripts/local_postgres/__main__.py` | Adds export database tests to the existing guarded `make test-postgresql` command. |
| `.env.example` | Documents optional destination and timeout variables without secrets. |
| `README.md`, `docs/SANDBOX_API.md`, `docs/LOCAL_POSTGRESQL.md`, `romi.md` | Link the outbound workflow and clarify the sandbox's deliberate real-Salesforce exception. |
