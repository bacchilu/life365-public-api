BEGIN;

CREATE TABLE public.customer_synchronization_versions (
    customer_id integer PRIMARY KEY
        REFERENCES public.customers (id) ON DELETE RESTRICT,
    resource_version bigint NOT NULL CHECK (resource_version > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.customer_synchronization_events (
    event_id uuid PRIMARY KEY,
    event_fingerprint bytea NOT NULL
        CHECK (octet_length(event_fingerprint) = 32),
    schema_version smallint NOT NULL CHECK (schema_version = 1),
    event_type text NOT NULL
        CHECK (event_type IN ('customer.created', 'customer.updated')),
    occurred_at timestamptz NOT NULL,
    resource_version bigint NOT NULL CHECK (resource_version > 0),
    result_success boolean NOT NULL,
    result_reference_id integer NOT NULL
        REFERENCES public.customers (id) ON DELETE RESTRICT,
    processed_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN public.customer_synchronization_events.event_fingerprint IS
    'HMAC-SHA256 of the canonical event with a stable secret; no event payload is stored';

COMMIT;
