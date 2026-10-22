-- Stop old synchronization writers before applying this migration and deploy
-- the version-free application before restarting them. Historical events must
-- not be replayed: their duplicate protection is intentionally removed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE public.customer_synchronization_events,
    public.customer_synchronization_versions IN ACCESS EXCLUSIVE MODE;

DELETE FROM public.customer_synchronization_events;
DROP TABLE public.customer_synchronization_versions;
ALTER TABLE public.customer_synchronization_events
    DROP COLUMN resource_version;

COMMIT;
