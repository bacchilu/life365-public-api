# Local PostgreSQL And Seeded Sandbox

## Scope

One Docker service, `local-postgres`, uses the explicit image `postgres:18.6`.
It replaces the old `customer-sync-test-db` service; it does not add a second
PostgreSQL server. Docker and host Python 3 are required for lifecycle commands.
The existing `.venv` and project dependencies are required for application and
test commands (`make build` prepares them).

The sandbox is a **small API-focused, sanitized production-derived fixture**,
not a full production clone. There is no dump, refresh, or production connection
at startup. No `sandbox-db-refresh`, `sandbox-db-up`, `sandbox-db-stop`, or
`sandbox-db-shell` Makefile targets are introduced.

The production `DATABASE_URL`, Caddy, and existing route behavior are unchanged.
The `/sandbox` FastAPI sub-application selects this database explicitly, with
separate authentication and disabled external business calls. See the
[sandbox API guide](SANDBOX_API.md). The scheduler retains its existing
configuration and does not automatically use the sandbox.

## Databases And Users

| Database | Owner/Login | Purpose | Default Local Password |
|---|---|---|---|
| `life365_sandbox` | `sandbox_user` | Seeded data for manual development | `sandbox_local_only` |
| `life365_public_api_test_customer_sync` | `customer_sync_test` | Empty database for automated PostgreSQL tests | `customer_sync_test` |
| `postgres` | `life365_local_admin` | Bootstrap and maintenance only | `local_admin_only` |

These are local development passwords, not production credentials. Override
them before starting the container on a shared workstation. Both application
roles are `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`. Each owns only its
own database. `PUBLIC` has no privileges on the two application databases, so
neither user can connect to the other's database. Public access to `postgres`
and `template1` is also revoked. Docker access remains administrative access;
these restrictions do not protect against a host user who controls Docker.

The sandbox's tables and synchronization event log are owned by `sandbox_user`.
The automated-test database has no application tables after initialization.
Existing test fixtures create, migrate, and remove tables there, never in the
sandbox. The helper supplies that exact test database and a dummy application
DSN to the test process; it never falls back to the production DSN.

## Connections And Networks

Only `127.0.0.1:55432` is published on the host. Container port `5432` is not
published on a public host interface. The project-scoped `local-database`
bridge network connects PostgreSQL to both `api-dev` and `life365-public-api`.
The production API also retains `life365-shared`; the development API retains
the default network. The scheduler's networks are unchanged.

From the host, open the sandbox directly with a PostgreSQL CLI:

```bash
psql -h 127.0.0.1 -p 55432 -U sandbox_user -d life365_sandbox
```

Enter the local sandbox password when prompted. Inside an API container, the
corresponding host and port are `local-postgres:5432`. These connection details
are documented for deliberate use; no Makefile command overwrites `DATABASE_URL`.

## Configuration

Compose reads `.env` and shell variables as usual. `.env.example` documents:

| Variable | Default | Effect |
|---|---|---|
| `LOCAL_POSTGRES_ADMIN_PASSWORD` | `local_admin_only` | Local bootstrap role password |
| `SANDBOX_DB_PASSWORD` | `sandbox_local_only` | Local sandbox role password |
| `CUSTOMER_SYNC_TEST_PASSWORD` | `customer_sync_test` | Dedicated test role password |
| `LOCAL_POSTGRES_TMPFS_SIZE` | `512m` | Maximum size of the database tmpfs mount |

The tmpfs limit is a ceiling, not an immediate 512 MB reservation. PostgreSQL
also uses RAM outside this mount for its processes and shared buffers. Tmpfs
can use swap. This small sample needs about 9 MB for its database, in addition
to PostgreSQL's cluster, WAL, and automated-test space. Increase the ceiling
only if a local workload needs it and the machine has sufficient memory.

Running containers retain their initial environment. The helper rejects a
password/environment mismatch instead of silently recreating the container.
To change these settings, explicitly stop and remove the local database
container, accepting loss of both databases, then start it again. Changing the
seed SQL also requires an empty database startup to take effect.

## Startup And Lifecycle

```bash
make run                  # Starts local PostgreSQL, then the native dev server
make docker-dev-up        # Starts local PostgreSQL, then API + scheduler
make docker-prod-up       # Starts local PostgreSQL, then detached API + scheduler
make docker-test-db-up    # Starts only the same shared local PostgreSQL service
make test-postgresql      # Runs PostgreSQL tests only in the dedicated test DB
```

The API services declare `depends_on: condition: service_healthy` for direct
Compose use. Make first starts/waits for PostgreSQL using the internal Python
helper, then starts only the selected API and scheduler with `--no-deps`.
Consequently an API rebuild does not recreate the temporary database container.
No `.venv` is needed merely to start/stop PostgreSQL; only standard-library
Python and Docker Compose are used by those helper actions.

The helper reuses a healthy running container without calling Compose `up`
again. It starts a stopped container with `docker start`, or creates a missing
container with `--no-recreate --wait`. It validates the Compose project/service,
image, tmpfs mount, localhost port binding, and local environment before reuse.
If an old `customer-sync-test-db` container still exists in this Compose
project, it refuses to start a second server. Explicitly remove that old
temporary container after checking whether its test data is still needed.

On empty storage, the image's initializer:

1. Creates the local roles and both databases.
2. Loads the versioned schema and sanitized rows into `life365_sandbox` as its
   unprivileged owner; no seed is loaded into the automated-test database.
3. Applies the project's existing synchronization migrations, in order, only
   to the sandbox. Its processed-event log starts empty.
4. Starts the final TCP server. The health check connects through TCP and
   checks that both databases exist, so it cannot report readiness during the
   earlier Unix-socket-only initialization server.

The helper fails if initialization fails or readiness times out. Inspect local
logs without changing or deleting the database automatically:

```bash
docker compose --profile test logs local-postgres
```

API shutdown does not stop PostgreSQL:

```bash
make docker-dev-down
make docker-prod-down
```

Those targets remove only their API and scheduler containers. Ctrl+C in
`make docker-dev-up` performs the same service-specific cleanup. They do not
use project-wide `down` and do not erase sandbox changes.

To intentionally discard both databases:

```bash
make docker-test-db-down
make docker-test-db-up
```

The first command warns and stops only `local-postgres`. Tmpfs contents vanish
when it stops. The second initializes the bundled sample again and an empty
test database, even though the container ID can be the same. Docker daemon
restarts and explicit container recreation also lose temporary data. Avoid
project-wide `docker compose down` or `--force-recreate` if local data is needed.

Concurrent helper operations use a nonblocking file lock under `.sandbox-db`.
The lock file stays on disk deliberately; the OS lock, not file existence,
indicates an active operation. Test runs hold the same lock to prevent a helper
stop command from erasing their database. Manual Docker commands and manually
launched pytest processes are not covered by this lock.

## Sample Provenance And Limits

Prepared on 2026-10-26 using bounded, read-only production queries. Four orders
were selected for each of `CONFIRMED`, `DELIVERED`, and `UNDELIVERABLE`, with
their linked customers, order lines, stock records, and products. Reference
catalogs and required category ancestors were included. No full data dump was
made; customer credentials and contact details were replaced. The local
`salesforce` account uses the same username and admin role as production,
but a separate local-only password. No production passwords are stored in
the seed.

| Table | Seed Rows |
|---|---:|
| `customers` | 7 |
| `orders` | 12 |
| `order_details` | 24 |
| `products` | 23 |
| `product_stocks` | 23 |
| `users` | 3 local application accounts |
| `agents` | 2 synthetic, non-personal agent records |
| `countries` | 39 |
| `regions` | 279 |
| `categories` | 23 |
| `sales_channels` | 20 |
| `payment_types` | 11 |
| `shop_groups` | 4 |

Customer/order/product/stock IDs are remapped without retaining a source ID
map. Customer names, company names, logins, passwords, emails, addresses, tax
identifiers, IP addresses, notes, banking details, geolocation, and arbitrary
customer JSON are replaced or removed. All original order dates, quantities,
prices, totals, descriptions, and customer references are replaced. The order
customer/detail/stock/product relationships and logistic/financial states are
retained; totals are recalculated from the sanitized line values. Public
catalog codes, product titles/specifications, and geographic/reference
catalogs are retained. Agent identities and credentials are never copied.

The remaining catalog and transaction relationships are production-derived;
review the fixture before distributing it outside the development team.

The selected 13 tables retain their production column shapes, but this is not
a complete production schema. IDs use local identity sequences, the relevant
local relationships are enforced, and production triggers, functions,
permissions, extensions, and unrelated tables are not included. Warehouse,
merchant, and tax-type IDs used by sample stocks/lines are local placeholders;
their complete tables/workflows are outside this fixture. Product brand IDs
are cleared. Extend the fixture before testing such unsupported workflows.

These application accounts are initialized inside the sandbox:

| Username | Password | Role / Principal Type |
|---|---|---|
| `sandbox-admin` | `sandbox-admin` | admin / user |
| `sandbox-buyer` | `sandbox-buyer` | buyer / user |
| `salesforce` | `romi` | admin / user |
| `sandbox-customer-1` through `sandbox-customer-7` | `sandbox-customer` | customer / customer |

The sandbox's `salesforce` account is a separate row in `public.users`, with
a local ID, role `ADMIN`, and `enabled = true`. It is included directly in
`docker/postgres/sandbox/data.sql` and is recreated with the other seed data
whenever PostgreSQL initializes its empty temporary storage. The other sample
accounts are synthetic and have no production counterparts.

Existing HTTP routes still authenticate using their original database, not these
sandbox rows. `/sandbox/auth/login` authenticates against the local rows instead.
Matching usernames on both sides does not share tokens or sessions. Explicit
sandbox settings and separate secrets are required; provisioning alone does not
enable sandbox HTTP operations. No external business service is called from the
sandbox; product recommendations return `501`.

## Files And Verification

- `docker-compose.yaml` provisions the shared server, readiness check, mounts,
  profiles, localhost port, and API networks.
- `docker/postgres/init-databases.sh` bootstraps both isolated users/databases
  and loads only the sandbox's files and synchronization migrations.
- `docker/postgres/sandbox/schema.sql` and `data.sql` are the reviewed,
  versioned subset and sanitized seed; these are not private production dumps.
- `scripts/local_postgres` implements guarded, serialized startup/stop and
  supplies the dedicated connection for the existing PostgreSQL test target.
- `Makefile` integrates those helpers into existing targets without introducing
  a refresh command or project-wide shutdown.
- `.env.example` documents local settings; `.gitignore` excludes real `.env`
  secrets while retaining the example. `.dockerignore` also excludes local locks
  and maintenance scripts from image builds.
- `tests/test_local_postgres.py` checks container reuse, startup flags,
  readiness failure, localhost/identity guards, locking, and target scope
  without connecting to any database.

Run `make test-postgresql` for the existing isolated database behavior tests
and `make test` for the full suite (database cases need the explicit dedicated
test connection). Never point these tests at the sandbox or production. The
tests deliberately create and drop tables in their dedicated database.
