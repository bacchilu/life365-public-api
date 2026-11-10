# Product Synchronization To Salesforce

These integration-only APIs export an existing Life365 catalog product to Salesforce.
They read the selected Life365 database and send one synchronous HTTP request;
they never write products, stock, or synchronization history locally.

## Endpoints

| Life365 method and path | Salesforce event | Life365 success status |
|---|---|---|
| `POST /integrations/salesforce/products/{product_id}` | `product.created` | 201 |
| `PUT /integrations/salesforce/products/{product_id}` | `product.updated` | 200 |
| `DELETE /integrations/salesforce/products/{product_id}` | `product.deleted` | 200 |

All three accept **no request body**. `product_id` means `products.id`, not
`product_stocks.id`, an EAN, or the Salesforce record ID. The product must exist
in the selected Life365 database. JWT authentication and the integration role are
required before any database lookup or remote call.

Normal routes use the unchanged `DATABASE_URL`. Routes with the `/sandbox`
prefix use only `life365_sandbox`, with its own credentials and token sessions.
Both environments make **real calls to the same configured Salesforce API**,
currently its UAT sandbox. The same numeric product ID targets the same remote
Product2 in both environments; sandbox IDs are not a separate remote namespace.

Salesforce receives all three events through HTTP **POST** to
`/services/apexrest/product/sync/`. Its documented create/update behavior is
upsert. The local HTTP method describes the event, not the remote HTTP method.
Salesforce currently returns HTTP 201 for all three event types.

## Product Mapping

| Payload field | Source and rule |
|---|---|
| `referenceId` | `products.id`, positive integer |
| `data.sku` | `products.isin`, never `vendor_code` or a stock SKU |
| `data.name` | Nonblank Italian title, otherwise English; required, at most 255 characters |
| `data.description` | Italian description, otherwise English, otherwise null; at most 4000 characters |
| `data.brand` | `brands.brand_name` resolved through `brand_id`; null when unassigned |
| `data.ean` | First valid stored EAN, following the rule below |
| `data.category` | Most specific assigned category, following the rule below |
| `data.productUrl` | `https://b2b.life365.eu/p/-{product_id}`, the existing portal catalog URL |
| `data.imageUrl` | First `product_images.image_url`, ordered by `id`, then URL; null without an image |
| `data.active` | `products.enabled`; a database null is treated as false, as in the existing product mapper |

PUT sends the **complete minimal DTO**, not a partial patch. Supplied nulls
clear optional remote values. No fields are truncated, no extra catalog fields
are added, and no prices or availability are inferred from stock rows.
Descriptions retain their stored text, including any HTML; overlong text is
rejected instead of silently shortened.

### EAN Selection

The adapter scans the JSON array `products.barcodes` in stored order and selects
the first ASCII-digit string with length 8 or 13 and a valid GS1 check digit.
Leading zeroes are preserved. Empty strings, all-zero placeholders, invalid
check digits, numeric JSON values, UPC/GTIN formats of other lengths, and
non-digit strings are not selected. Whitespace is not repaired.

No candidate means `ean: null`; invalid entries generate a warning with the
product reference and discarded count. An invalid array also generates a
warning and becomes null. The database is unchanged. No code is generated
from the product ID, and no digits are added or corrected. Additional valid
EANs remain in Life365; the minimal Salesforce DTO carries only one.
This is a format/check-digit check, not verification of GS1 assignment.

### Category Selection

Choose the first non-null identifier in `level_3`, `level_2`, `level_1` and
resolve that exact `categories` row. A missing referenced row is an error,
not a reason to silently select another category. `code` is that category ID
as a string, while `name` is its nonblank Italian name, then English.
The name is required when a category is assigned.

When all three identifiers are absent, send `category: null`. No slug, new
category code column, or hierarchy object is introduced. For sandbox product
101, the payload includes:

```json
{
  "ean": "0700443238779",
  "category": {"code": "1005", "name": "Samsung Laserjet"}
}
```

## Deactivation And Reactivation

DELETE sends `product.deleted` without a `data` property. Salesforce sets
`IsActive=false`; its product remains for order history. Life365's product,
including `enabled`, is unchanged. Only local existence is checked, so a
missing title or an invalid brand/category does not block remote deactivation.

To reactivate, ensure the local product has `enabled=true`, then call PUT.
The current full snapshot includes `active=true`. DELETE of a nonexistent
remote product returns 404; it does not silently report success.

The [order export](SALESFORCE_ORDER_EXPORT.md) resolves
`order_details.product_stock_id -> product_stocks.product_id -> products.id`
and use that final ID as `productReferenceId`.

## Configuration

Reuse `SALESFORCE_TOKEN_URL`, `SALESFORCE_CLIENT_ID`,
`SALESFORCE_CLIENT_SECRET`, and `SALESFORCE_TIMEOUT_SECONDS` (default 30).
The access token is cached in process memory and shared with customer exports.
Callers provide a Life365 JWT, not a Salesforce access token.

`SALESFORCE_PRODUCT_SYNC_URL` is optional. If absent, the endpoint is the
token URL's origin plus `/services/apexrest/product/sync/`. A configured URL
must be HTTPS, have the same origin as authentication, and contain no embedded
credentials, query, or fragment. Secrets are not logged or returned.

The default needs no change to an existing `.env`. Selecting a different
Salesforce instance later requires updating the shared OAuth configuration
and any explicitly configured synchronization URLs together.

## Sandbox Schema Setup

Fresh local PostgreSQL initialization includes `brands` and `product_images`
through `docker/postgres/sandbox/product-export-support.sql`. The existing
sanitized catalog and its IDs are unchanged; its unassigned brands and absent
images remain null. The production database already has these tables; this
change does not require a production migration.

An **already running** sandbox created before this feature needs the additive
script once. After updating the checkout, run this against the intended local
Compose project, without restarting PostgreSQL or resetting either database:

```bash
docker compose --profile test exec -T local-postgres sh -c \
  'PGPASSWORD="$SANDBOX_DB_PASSWORD" psql -X -U sandbox_user \
  -d life365_sandbox -v ON_ERROR_STOP=1 \
  --file /opt/life365-sandbox/product-export-support.sql'
```

When managed by `life365-portal-stack`, use that stack's Compose project and
override files for the same `local-postgres` service. Do not accidentally start
a second project. The script is idempotent and refuses database names other
than `life365_sandbox` and the dedicated automated-test database. It does not
populate production brands/images or copy customer data.

Stopping PostgreSQL still loses both temporary databases. The next start loads
the bundled sanitized sample and the support tables again.

## Curl Examples

These examples use the deployed Life365 sandbox and its synthetic integration
credentials. Set `API_URL=http://127.0.0.1:8000/sandbox` for native local testing.
New code must be deployed before the new endpoints exist on the server.

```bash
API_URL='https://b2b.life365.eu/public-api/sandbox'
AUTH_TOKEN=$(curl --fail-with-body -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{"username":"salesforce","password":"romi","principal_type":"user"}' \
  | jq -er '.access_token')
PRODUCT_ID=101
```

Create the Salesforce representation of the existing sandbox product:

```bash
curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

After editing Life365, send its current full shared data:

```bash
curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Deactivate only the Salesforce record:

```bash
curl --fail-with-body -sS -X DELETE \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

All three return:

```json
{
  "success": true,
  "eventId": "<EVENT_UUID>",
  "referenceId": 101,
  "recordId": "<SALESFORCE_PRODUCT2_ID>"
}
```

For normal production data, use `https://b2b.life365.eu/public-api` and obtain
a normal integration-role token. Admin, buyer, and customer roles cannot call
these APIs. Sandbox credentials and tokens do not work on normal routes.

## Delivery And Errors

Every call generates a new `eventId` and UTC `occurredAt`. `schemaVersion`
remains 1; `resourceVersion` is never emitted. Event time is metadata, not an
ordering mechanism. Send operations for one product sequentially and wait for
success; different products can be synchronized concurrently.

There is no outgoing event table, queue, outbox, or durable retry state. Only
upstream HTTP 401 triggers one token renewal and retransmission of the identical
event. Other errors, connection failures, and timeouts are not retried. Check
the remote result before manually repeating an uncertain operation, since
a new Life365 call generates a new event. Logs identify event and product IDs,
without dumping credentials, access tokens, or remote response bodies.

| Life365 status | Meaning |
|---|---|
| 401 / 403 | Invalid Life365 token / integration role required, including for admins |
| 404 | Local product absent, or remote product absent on DELETE |
| 409 | Salesforce reports a conflict |
| 422 | Invalid ID/body or unrepresentable title, description, brand, or category |
| 502 | Salesforce authentication, delivery, or response validation failed |
| 503 | Local database unavailable or Salesforce configuration invalid |
| 504 | Salesforce timeout; remote outcome may be unknown |

A successful remote response must match the submitted `eventId` and
`referenceId` and include a nonblank `recordId`. Otherwise the API reports a
failure rather than claiming synchronization succeeded.

## Verification

Run `make test` for unit/HTTP tests. Salesforce HTTP uses `httpx.MockTransport`.
Run `make test-postgresql` for the guarded isolated database tests. These check
real PostgreSQL mapping and authenticated routes while mocking Salesforce;
they never use production or reset the seeded sandbox.

Live checks performed before implementation verified create, partial update,
deactivation, and reactivation through the custom Salesforce endpoint.
Current credentials cannot read the proposed custom Product2 fields or query
PricebookEntry. Their persistence and automatic zero-price list entry remain
unverified; an accepted event alone does not establish those values were saved.
Remote acceptance of `category: null` is covered by simulated transport tests,
not by a live call. No live Salesforce business writes are needed to run tests.

## Implementation Files

| File | Responsibility |
|---|---|
| `app/application/dtos/product_integration.py` | Immutable product/category/event/result types, independent of HTTP and PostgreSQL |
| `app/application/ports.py` | Reader and Salesforce gateway protocols for constructor injection |
| `app/application/exceptions.py` | Product missing/reference/data errors, without HTTP status codes |
| `app/application/services/product_export_service.py` | Read or existence check, event creation, gateway delegation, result checks, correlated logs |
| `app/infrastructure/data_mapper/product_export/__init__.py` | Explicit read-only PostgreSQL connections and safe persistence errors |
| `app/infrastructure/data_mapper/product_export/query.py` | Parameterized catalog/reference/image query and lightweight existence lookup |
| `app/infrastructure/data_mapper/product_export/product.py` | Local-to-shared mapping, languages, category and brand resolution, portal URL, length checks |
| `app/infrastructure/data_mapper/product_export/barcode.py` | Deterministic EAN selection, checksum validation, discard warnings |
| `app/infrastructure/salesforce/product_payload.py` | JSON aliases, complete snapshots, UTC metadata, delete without data |
| `app/infrastructure/salesforce/product_client.py` | Real HTTP delivery, one 401 retry, safe errors and response validation |
| `app/infrastructure/salesforce/settings.py` | Optional product endpoint and same-origin HTTPS validation |
| `app/infrastructure/salesforce/auth.py` | Existing shared process token cache; authentication messages now apply to any event |
| `app/infrastructure/salesforce/__init__.py` | Expose the new concrete product adapter |
| `app/api/integrations/product_exports.py` | POST/PUT/DELETE, no-body/path validation, response schema, HTTP errors, OpenAPI |
| `app/api/integrations/product_export_dependencies.py` | Shared integration-role dependency, normal database reader and lazy real gateway composition |
| `app/api/integrations/__init__.py` | Register the new routes for both applications |
| `app/api/sandbox/services.py` | Build the service with the explicit sandbox connection and shared remote gateway |
| `app/api/sandbox/__init__.py` | Application-local dependency override and sandbox description |
| `docker/postgres/sandbox/product-export-support.sql` | Guarded additive brand/image lookup tables for sandbox/test only |
| `docker/postgres/init-databases.sh` | Apply the support SQL during fresh sandbox initialization |
| `scripts/local_postgres/__main__.py` | Include product export in the existing guarded PostgreSQL test command |
| `tests/test_sandbox_postgresql.py` | Load and clean up support tables only in the isolated test fixture |
| `tests/test_product_export_mapping.py` | EAN, localization, nullable metadata and invalid-reference mapping tests |
| `tests/test_product_export_service.py` | Event dispatch, missing products, lightweight delete, failures and event identity tests |
| `tests/test_salesforce_product_api.py` | Simulated OAuth, payloads, retries, token sharing, remote failures, result/config validation |
| `tests/test_product_export_api.py` | Routes, integration/token guards, database separation, body/path validation, errors and proxy OpenAPI |
| `tests/test_product_export_postgresql.py` | Real isolated PostgreSQL reads, references, category fallback, HTTP flows and unchanged local state |
| `.env.example` | Document optional product endpoint without adding real credentials |
| `README.md` | Entry point and concise examples for the new functionality |
| `docs/integrations/SALESFORCE_PRODUCT_EXPORT.md` | Complete contract, operational guide, verification limits and file responsibility map |
