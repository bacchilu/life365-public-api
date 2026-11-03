"""Read product metadata, brand, category and first image in one snapshot."""

from psycopg import sql

PRODUCT_QUERY = sql.SQL("""
SELECT p.id, p.isin, p.titles, p.descriptions, p.enabled, p.barcodes,
       p.brand_id, b.id AS resolved_brand_id, b.brand_name,
       COALESCE(p.level_3, p.level_2, p.level_1) AS selected_category_id,
       c.id AS resolved_category_id, c.name AS category_names,
       (SELECT i.image_url FROM public.product_images AS i
        WHERE i.product_id = p.id ORDER BY i.id, i.image_url LIMIT 1) AS image_url
FROM public.products AS p
LEFT JOIN public.brands AS b ON b.id = p.brand_id
LEFT JOIN public.categories AS c
  ON c.id = COALESCE(p.level_3, p.level_2, p.level_1)
WHERE p.id = %(reference_id)s
""")

PRODUCT_EXISTS_QUERY = sql.SQL("""
SELECT EXISTS(SELECT 1 FROM public.products WHERE id = %(reference_id)s)
""")
