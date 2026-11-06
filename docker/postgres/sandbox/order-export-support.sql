-- Reuse the existing Life365 ADMGST convention with a local generated ID.
-- Add sample data only; never copy the real production product ID.
BEGIN;

DO $$
BEGIN
    IF current_database() NOT IN (
        'life365_sandbox', 'life365_public_api_test_customer_sync'
    ) THEN
        RAISE EXCEPTION 'Order export support must target a local sandbox or test database';
    END IF;
END
$$;

INSERT INTO public.products (vendor_code, isin, titles, descriptions, enabled)
SELECT '', 'ADMGST',
       '{"it":"Spese amministrative","en":"Administrative charges"}'::jsonb,
       '{"en":"Sanitized service product for shipping export"}'::jsonb, true
WHERE NOT EXISTS (SELECT 1 FROM public.products WHERE isin = 'ADMGST');

COMMIT;
