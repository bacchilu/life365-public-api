"""Keep missing references visible; never filter historical/virtual products."""

ORDER_QUERY = """
SELECT o.*, c.id AS resolved_customer_id,
       dr.region_name AS delivery_region_name,
       dc.iso_alpha_2 AS delivery_country_code,
       br.region_name AS billing_region_name,
       bc.iso_alpha_2 AS billing_country_code
FROM public.orders AS o
LEFT JOIN public.customers AS c ON c.id = o.customer_id
LEFT JOIN public.regions AS dr ON dr.id = o.delivery_region_id
LEFT JOIN public.countries AS dc ON dc.id = dr.country_id
LEFT JOIN public.regions AS br ON br.id = o.region_id
LEFT JOIN public.countries AS bc ON bc.id = br.country_id
WHERE o.id = %(reference_id)s
"""

DETAILS_QUERY = """
SELECT od.id, od.product_stock_id, od.qty, od.price, od.product_description,
       p.id AS product_id, p.isin
FROM public.order_details AS od
LEFT JOIN public.product_stocks AS ps ON ps.id = od.product_stock_id
LEFT JOIN public.products AS p ON p.id = ps.product_id
WHERE od.order_id = %(reference_id)s
ORDER BY od.id
"""

SHIPPING_QUERY = (
    "SELECT id, isin FROM public.products WHERE isin = 'ADMGST' ORDER BY id"
)

ORDER_EXISTS_QUERY = (
    "SELECT EXISTS (SELECT 1 FROM public.orders WHERE id = %(reference_id)s)"
)
