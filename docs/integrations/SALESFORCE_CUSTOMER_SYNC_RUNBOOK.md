# Salesforce Customer Synchronization

## Configure The Backend

`POST /integrations/salesforce/events` accepts `customer.created` and
`customer.updated` from authenticated admins. It uses the in-memory backend
unless `CUSTOMER_SYNC_BACKEND=postgresql` is set. In-memory customer and event
state is lost on restart and is not shared between workers.

Before enabling PostgreSQL:

1. Verify the database identity using the configured `DATABASE_URL`. Apply
   migrations in order. On an existing installation where migration 0001 has
   already been applied, apply only migration 0002. Do not rewrite or rerun
   migration 0001. The database must already contain the Life365 customer and
   reference tables. With `DATABASE_URL` exported in the shell:

   ```bash
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
     -c 'SELECT current_database(), current_user, inet_server_addr(), inet_server_port();'
   # New installation only:
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f migrations/0001_customer_synchronization.sql
   # Both new and existing installations:
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
     -f migrations/0002_remove_customer_resource_versions.sql
   ```

2. Set `CUSTOMER_SYNC_FINGERPRINT_SECRET` to a stable random value of at least
   32 bytes. Keep the same value across workers, restarts, and deployments.
   Changing it makes previously processed events fail fingerprint checks on
   retry. This secret is separate from `JWT_SECRET_KEY`. The database stores an
   HMAC fingerprint of each event, not its raw payload or password.
3. Set `CUSTOMER_SYNC_BACKEND=postgresql` in the API environment and restart
   the API. The scheduler does not process incoming customer events.
4. Configure the reverse proxy and Uvicorn to trust forwarded client addresses
   only from that proxy. Uvicorn reads `FORWARDED_ALLOW_IPS` from its process
   environment. Use specific proxy addresses, not `*`. A create event requires
   a trusted IPv4 client address for `customers.registration_ip`; update events
   never change that column.

The API does not apply the migration automatically. On a database error it
returns `503`; do not enable PostgreSQL mode before the migration is present.
Existing customers can receive updates using their Life365 `referenceId`
without any prior synchronization history or version-state record.

## Upgrade And History Reset

Migration 0002 clears `public.customer_synchronization_events`, drops
`public.customer_synchronization_versions`, and removes the event table's
`resource_version` column. It preserves customers, the remaining event columns,
and the primary-key and fingerprint constraints. It uses one transaction, no
`CASCADE`, a five-second lock timeout, and a thirty-second statement timeout.
If it fails, investigate and retry; do not partially apply its statements.

Pause Salesforce delivery and stop every old API worker or other customer-sync
writer before running the migration. Resolve uncertain in-flight events first.
Deploy the new code while delivery remains paused, apply migration 0002, then
start only compatible workers and resume with new events. Old code cannot use
the new schema; new code must not run against the old schema. Back up the event
history first if required for audit, without copying raw payloads or passwords.

**Clearing event history removes duplicate protection for every event processed
before the reset. Historical create or update events must not be replayed as if
their history still existed.** A historical create can otherwise create another
customer or fail a login conflict; an old update could overwrite newer data.
Coordinate this boundary with Salesforce. The API does not retain compatibility
with old fingerprints. Requests containing `resourceVersion` now fail with 422;
`schemaVersion` remains 1.

## Send A Full Create Event

Log in as an internal admin and keep the returned `access_token`:

```bash
API_URL=http://127.0.0.1:8000
curl --fail-with-body -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "<admin-login>",
    "password": "<admin-password>",
    "principal_type": "user"
  }'
```

The synthetic fixture contains every required create field. Use it only with
an isolated test database; replace its login, password, other customer data,
and `eventId` for a real customer. Keep the exact request body for retries.

```bash
ACCESS_TOKEN='<JWT-from-login>'
curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/events" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @tests/fixtures/integrations/salesforce/customer-created-v1.json
```

A successful create returns HTTP 200 with `success: true`, the submitted
`eventId`, and the new Life365 customer ID in `referenceId`. PostgreSQL mode
returns success only after the customer and event result
commit in one transaction.

## Send A Partial Update Event

Use the `referenceId` returned by create and a new UUID for this event:

```bash
REFERENCE_ID='<referenceId-from-create>'
UPDATE_EVENT_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/events" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<JSON
{
  "schemaVersion": 1,
  "eventId": "$UPDATE_EVENT_ID",
  "occurredAt": "2026-09-28T10:00:00Z",
  "eventType": "customer.updated",
  "referenceId": $REFERENCE_ID,
  "data": {
    "company": {"website": null},
    "commercial": {"paymentDays": 0},
    "notes": {"items": []}
  }
}
JSON
```

The update clears `company.website`, sets payment days to zero, and replaces
the notes array with an empty array. It leaves every omitted field unchanged.
See [the event contract](SALESFORCE_CUSTOMER_EVENTS_V1.md) for nested patch and
JSON Merge Patch rules.

## Retry And Failure Rules

- Retry a request with the same `eventId` and identical complete content,
  including `occurredAt` and `data`. A committed event
  returns its original result without another customer change.
- Reusing an `eventId` with different content returns `409`.
- Serialize events for each customer. Wait for success before sending the next
  event for that customer. After a timeout or uncertain result, retry the same
  event with identical content before proceeding. Different customers can be
  synchronized concurrently. `occurredAt` is metadata, not an ordering key;
  there is no version counter or stale-event rejection.
- An unknown `referenceId` returns `404`. Invalid customer references return
  `400`. Invalid request or database mapping data returns `422`.
- Missing or invalid bearer tokens return `401`; non-admin roles return `403`.
  Persistence failures return `503` and roll back the customer and
  event together. Retry an uncertain `503` with the same event body and ID.

For validated events, API logs include `event_id`, `reference_id`,
`event_type`, and HTTP status. A create failure logs
`reference_id=None` because no customer ID was committed. Logs exclude the
request payload, password, JWT, and fingerprint secret. Search by `event_id`
first, then use `reference_id` to follow later updates.
