# Order Synchronization To Salesforce

## Endpoints And Boundaries

| Local method and route | Remote event | Local success |
|---|---|---|
| `POST /integrations/salesforce/orders/{order_id}` | `order.created` | 201 |
| `PUT /integrations/salesforce/orders/{order_id}` | `order.updated` | 200 |
| `DELETE /integrations/salesforce/orders/{order_id}` | `order.deleted` | 200 |

All methods require a Life365 JWT and admin role, reject a nonempty body,
and require an existing local orders.id. Normal routes use the unchanged
DATABASE_URL; /sandbox routes use only life365_sandbox. Both send real requests
to the same configured Salesforce UAT API. Numeric order references share one
remote namespace: sandbox exports can overwrite a matching remote order.

All remote deliveries are POST to /services/apexrest/order/sync/, per section 7
of ROMI's [Integrazione-Salesforce-LIFE365.docx](Integrazione-Salesforce-LIFE365.docx).
POST/PUT send the complete minimal snapshot, including all lines. Supplied
lines replace the remote list. ROMI
documents create/update as upserts. DELETE sends no data, marks
Life365_Status__c=deleted and retains history. No local data is modified,
including on DELETE or remote failure.

The Account for customerReferenceId must already be synchronized; otherwise
Salesforce returns 404. There is no implicit customer export. ROMI documents
provisional Product2 creation for missing line products; later product exports
complete them. The application never creates local catalog records during export.

## Mapping

| Payload | Source and rule |
|---|---|
| schemaVersion | Fixed 1; resourceVersion is absent |
| eventId / occurredAt | New UUID and timezone-aware UTC metadata per call |
| referenceId | orders.id |
| customerReferenceId | orders.customer_id; local customer must resolve |
| orderNumber | String form of orders.id, not customer_reference or invoice number |
| status | Unchanged, nonblank orders.logistic_state |
| orderDate | Stored order_date; historical naive timestamps interpreted as UTC |
| invoice | Number/date from invoice_doc_n/invoice_doc_date, or null; URL null |
| shippingAddress | Stored delivery address with resolved region/country; fallback to stored billing address only when delivery address is entirely null; null if both absent |
| notes | orders.note, including null |
| lines[].lineId | String form of order_details.id, ordered by that ID |
| lines[].productReferenceId | product_stock_id -> product_stocks.product_id -> products.id |
| lines[].sku | products.isin, not stock ID or vendor_code |
| lines[].description | Historical order_details.product_description |
| lines[].quantity | Stored qty, strictly positive |
| lines[].unitPrice | Absolute stored price, nonnegative |
| lines[].lineTotal | Signed stored price times qty |

No date or state eligibility filter is imposed on export by ID. GET /orders
retains its existing CONFIRMED/DELIVERED/UNDELIVERABLE filter. Export does not
change financial/invoice states, stock, fulfillment or local logistic state.
The Salesforce standard Order.Status is managed remotely, not mapped to its
restricted picklist here.

Naive-UTC conversion follows existing historical Life365 readers, not machine
local time. This does not prove every external historical writer used UTC.
Incomplete invoice/address references fail instead of silently disappearing.
No current customer address or public invoice PDF URL is invented.

## Monetary Rules

Use Decimal throughout and two-decimal JSON strings, never floats:

```text
net   = sum(order_details.price * qty) + orders.delivery_cost
gross = orders.total
tax   = gross - net
```

Tax is the combined historical residual, not necessarily VAT alone. This keeps
tax2 and the rounding already included in gross. Portal cart and recalculation
paths round differently, so current rates must not be reapplied to old orders.
No fixed 22% assumption is made. This preserves recorded amounts; it is not an
independent fiscal audit of stored gross or a reconstruction of the VAT/tax2 split.

Keep virtual, disabled, voucher, administrative and discount detail lines.
Do not reapply perbox_discount/row_discount or send discountPercent: discount
collectors already persist those amounts.

Goods 100.00, discount -10.00 and shipping 5.00 yield net 95.00. With recorded
gross 115.90, tax is 20.90. The discount line has unitPrice 10.00 and lineTotal
-10.00. Consumers must use signed lineTotal/custom totals, not the sum of
nonnegative standard UnitPrice values.

The explicit live UAT probe on 2026-11-05 returned HTTP 201 for negative
lineTotal with positive unitPrice. The integration user could not read
Order/OrderItem, so the saved negative field was not independently verified.
ROMI must preserve that signed field; request acceptance alone is not proof.

Nonzero header stamp_duty is rejected with 422 because its inclusion in the
historical gross is not established. Null/zero means no separate header amount
to export. An existing ST-DUTY detail remains an ordinary signed line and is
not added twice. Missing totals, non-finite/sub-cent prices, nonpositive
quantities and broken product references fail before remote delivery.

## Shipping

Positive delivery_cost appends one line:

```text
lineId             shipping-{orders.id}
productReferenceId products.id for the unique products.isin = ADMGST
sku                ADMGST
description        Spese di spedizione
quantity           1
unitPrice          orders.delivery_cost
lineTotal          orders.delivery_cost
```

The portal credit-note reader already uses ADMGST for shipping. A read-only
production lookup found ID 14232, but that ID is not hardcoded. Resolve the SKU
in the selected database; missing/ambiguous results fail with 422. Zero shipping
emits no extra line. Existing ADMGST details remain separate administrative
charges; never remove or merge them with header delivery_cost.

Fresh local initialization adds a sanitized ADMGST product with a local generated
ID, without stock or changed sample-order money. The catalog now has 24 products.
Sample orders retain their simplified gross equal to signed line sums; zero
residual is not evidence of a real zero-VAT regime.

For an already running local sandbox, apply the additive script without restarting:

```bash
docker compose --profile test exec -T local-postgres sh -c \
  'PGPASSWORD="$SANDBOX_DB_PASSWORD" psql -X -U sandbox_user \
  -d life365_sandbox -v ON_ERROR_STOP=1 \
  --file /opt/life365-sandbox/order-export-support.sql'
```

Use the actual project/override files when managed by life365-portal-stack.
The script is idempotent, guards local database names and is not a production
migration. Never reset PostgreSQL to load it: tmpfs contents would be lost.
Production already has its ADMGST product.

## Configuration, Delivery And Errors

Reuse SALESFORCE_TOKEN_URL, SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET,
SALESFORCE_TIMEOUT_SECONDS and the process-local token cache shared with customer
and product exports. Optional SALESFORCE_ORDER_SYNC_URL defaults to the token
origin plus /services/apexrest/order/sync/. Overrides require HTTPS, same origin,
and no credentials/query/fragment. Default URLs need no existing .env changes.

Only an explicit remote HTTP 401 permits one OAuth renewal and retransmission
of the identical payload/eventId. A second 401 clears the token and fails.
Timeouts, connection failures, other statuses and redirects are not retried.
No outgoing table, queue, worker, automatic trigger or general retry is added.
Each client call is a new event. Serialize calls per order. After an uncertain
response check Salesforce before repeating: it may already have committed.
The read transaction ends before HTTP; this is not a distributed transaction.

Success requires HTTP 200/201, success=true, matching eventId/referenceId and
nonblank recordId. Local responses contain success, eventId, referenceId,
recordId. Logs contain event/reference/type/status, never payloads or credentials.

| Local status | Meaning |
|---|---|
| 401 / 403 | Invalid/wrong-environment token / non-admin role |
| 404 | Local order missing, remote customer not synchronized, remote order missing on DELETE |
| 409 | Salesforce uniqueness conflict |
| 422 | Invalid ID, body present, unrepresentable source or unsupported header stamp |
| 502 | Remote authentication/delivery/response error; no raw remote body exposed |
| 503 | Database/configuration unavailable |
| 504 | Remote timeout; outcome uncertain |

## Usage And Verification

The Italian [Life365 guide](../../life365.md#sincronizzazione-degli-ordini)
contains authentication, customer-first, POST, PUT and DELETE curl examples.
Use http://127.0.0.1:8000/sandbox locally. Deployed routes require deploying
this code first; no Caddy change is needed.

Run `make test` without a configured isolated PostgreSQL URL for the ordinary
suite. `make test-postgresql` includes the guarded database suite. Never target
production or the seeded sandbox with destructive automated fixtures.
All automated remote calls use MockTransport. No new live Salesforce writes
are required by or performed in these automated tests.

Verified locally on 2026-11-06:
- Import organization, formatting and configured lint pass for every changed
  Python file using Ruff.
- Full suite with a dummy DATABASE_URL and no test DSN: 1437 passed, 68 skipped.
- `make test-postgresql`: 75 passed, 2 skipped, using only
  life365_public_api_test_customer_sync. Skipped cases retain their existing
  optional prerequisites.
- Native HTTP: both Swagger/OpenAPI documents show the three order methods;
  sandbox health, admin login/logout and reads work (12 orders, 24 products,
  local ADMGST ID 124). Anonymous exports return 401 without delivery.
- Documentation shell examples parse and local links resolve.

The local test interpreter is Python 3.14.8; the Docker image remains pinned
to Python 3.15.2. This task did not rebuild/deploy that image or run new real
Salesforce export calls. Production was used only for the requested read-only
service-product lookup; no production data/schema/configuration was modified.

## File Responsibilities

| File | Responsibility |
|---|---|
| app/application/dtos/order_integration.py | Frozen/slotted invoice, totals, line, snapshot, event and result types, no framework dependencies |
| app/application/ports.py | Typed order reader/existence and remote send protocols |
| app/application/exceptions.py | Missing order, invalid reference and source-data errors |
| app/application/services/order_export_service.py | Dispatch, source read, fresh event, safe logs, checked result; existence-only delete |
| app/infrastructure/data_mapper/order_export/query.py | Parameterized header/references, left-joined details, shipping and existence SQL |
| app/infrastructure/data_mapper/order_export/__init__.py | Explicit read-only REPEATABLE READ snapshot across all source queries; safe DB exceptions |
| app/infrastructure/data_mapper/order_export/values.py | Exact amounts, IDs, text and UTC conversion |
| app/infrastructure/data_mapper/order_export/order.py | Historical invoice/address, signed rows, shipping, stored totals and validation |
| app/infrastructure/salesforce/order_payload.py | Explicit camelCase JSON, decimal strings, UTC and data-free delete |
| app/infrastructure/salesforce/order_client.py | Actual async HTTP, shared auth, single 401 retry and strict response checks |
| app/infrastructure/salesforce/settings.py | Optional/default same-origin order URL |
| app/infrastructure/salesforce/__init__.py | Publish the order adapter |
| app/api/integrations/order_exports.py | Three routes, schema, guards, API-only exception translation, Swagger |
| app/api/integrations/order_export_dependencies.py | Normal database reader and lazy shared remote client |
| app/api/integrations/__init__.py | Register the router in both applications |
| app/api/sandbox/services.py | Sandbox-only order reader with the same real remote client |
| app/api/sandbox/__init__.py | App-local order service override and scope description |
| .env.example | Document optional URL without credentials |
| docker/postgres/sandbox/order-export-support.sql | Guarded, additive synthetic service product |
| docker/postgres/init-databases.sh | Include support during empty-storage initialization |
| scripts/local_postgres/__main__.py | Register database tests with the existing Make target |
| tests/test_sandbox_postgresql.py | Same support in the isolated, destination-guarded fixture |
| tests/test_order_export_mapping.py | Monetary/reference/address/invoice/UTC/source validation |
| tests/test_order_export_service.py | Typed dispatch, IDs, safe logs, failures and result validation |
| tests/test_order_export_api.py | Role/token isolation, methods, body guards, errors, composition and proxy OpenAPI |
| tests/test_salesforce_order_api.py | Mocked contract, OAuth/cache, exact 401 retry, errors, response mismatch and URL safety |
| tests/test_order_export_postgresql.py | Real isolated DB mapping, unchanged state, concurrent source edits under snapshot, authenticated mock-remote flow and seed idempotency |
| life365.md | Italian operational examples and business rules |
| README.md | Entry points and updated seed count |
| docs/SANDBOX_API.md | Shared routes and real outbound order exception |
| docs/LOCAL_POSTGRESQL.md | Service-product sample provenance/count |
| docs/integrations/SALESFORCE_PRODUCT_EXPORT.md | Link the implemented order export instead of describing it as future work |

