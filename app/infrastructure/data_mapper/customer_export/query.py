"""Read the complete customer and references in one PostgreSQL snapshot."""

from psycopg import sql

CUSTOMER_QUERY = sql.SQL("""
SELECT c.*,
       br.region_name AS billing_region_name, bc.iso_alpha_2 AS billing_country_code,
       dr.region_name AS delivery_region_name, dc.iso_alpha_2 AS delivery_country_code,
       a.user_login AS agent_login, a.contact_name AS agent_name,
       a.email AS agent_email, a.phone AS agent_phone,
       sc.c_name AS channel_name,
       (SELECT jsonb_agg(jsonb_build_object('id', entry.id, 'name', cat.name) ORDER BY entry.position)
        FROM unnest(c.preferred_categories) WITH ORDINALITY AS entry(id, position)
        LEFT JOIN public.categories AS cat ON cat.id = entry.id) AS export_categories,
       (SELECT jsonb_agg(jsonb_build_object('id', entry.id, 'name', sg.group_name) ORDER BY entry.position)
        FROM unnest(c.shop_group_ids) WITH ORDINALITY AS entry(id, position)
        LEFT JOIN public.shop_groups AS sg ON sg.id = entry.id) AS export_groups
FROM public.customers AS c
LEFT JOIN public.regions AS br ON br.id = c.region_id
LEFT JOIN public.countries AS bc ON bc.id = br.country_id
LEFT JOIN public.regions AS dr ON dr.id = c.delivery_region_id
LEFT JOIN public.countries AS dc ON dc.id = dr.country_id
LEFT JOIN public.agents AS a ON a.id = c.agent_id
LEFT JOIN public.sales_channels AS sc ON sc.id = c.sales_channel_id
WHERE c.id = %s
""")
