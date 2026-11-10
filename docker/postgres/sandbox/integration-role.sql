-- Upgrade only the seeded integration account; never reset a sandbox.
BEGIN;

DO $$
BEGIN
    IF current_database() NOT IN (
        'life365_sandbox', 'life365_public_api_test_customer_sync'
    ) THEN
        RAISE EXCEPTION 'Integration role upgrade must target a sandbox or test database';
    END IF;

    LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE;

    IF (SELECT count(*) FROM public.users WHERE username = 'salesforce') <> 1 THEN
        RAISE EXCEPTION 'Expected exactly one sandbox salesforce account';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.users
        WHERE username = 'salesforce'
          AND role IN ('ADMIN', 'INTEGRATION')
          AND enabled IS TRUE
    ) THEN
        RAISE EXCEPTION 'Unexpected role or disabled sandbox salesforce account';
    END IF;

    UPDATE public.users SET role = 'INTEGRATION'
    WHERE username = 'salesforce' AND role = 'ADMIN';
END
$$;

COMMIT;
