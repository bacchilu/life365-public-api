#!/bin/sh
set -eu

psql -X --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 \
    --set sandbox_password="$SANDBOX_DB_PASSWORD" \
    --set test_password="$CUSTOMER_SYNC_TEST_PASSWORD" <<'SQL'
CREATE ROLE sandbox_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION PASSWORD :'sandbox_password';
CREATE ROLE customer_sync_test LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION PASSWORD :'test_password';

CREATE DATABASE life365_sandbox OWNER sandbox_user TEMPLATE template0;
CREATE DATABASE life365_public_api_test_customer_sync
    OWNER customer_sync_test TEMPLATE template0;
REVOKE ALL ON DATABASE life365_sandbox FROM PUBLIC;
REVOKE ALL ON DATABASE life365_public_api_test_customer_sync FROM PUBLIC;
REVOKE CONNECT ON DATABASE postgres, template1 FROM PUBLIC;

SQL

PGPASSWORD="$SANDBOX_DB_PASSWORD" psql -X \
    --username sandbox_user --dbname life365_sandbox --set ON_ERROR_STOP=1 \
    --file /opt/life365-sandbox/schema.sql \
    --file /opt/life365-sandbox/data.sql \
    --file /opt/life365-migrations/0001_customer_synchronization.sql \
    --file /opt/life365-migrations/0002_remove_customer_resource_versions.sql
