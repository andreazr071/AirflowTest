-- Reconstruye el neto diario por producto a partir de los hechos.
-- Revenue neto = revenue bruto - monto de devoluciones/ajustes del MISMO código de producto
-- en el MISMO día (UTC). Se ejecuta dentro de la transacción de carga (ver warehouse.py).
TRUNCATE dw.agg_daily_product_net;

INSERT INTO dw.agg_daily_product_net
    (invoice_date, product_code, units_sold, units_returned, gross_revenue, returned_amount, net_revenue)
WITH sales AS (
    SELECT invoice_date, product_code,
           SUM(quantity)      AS units_sold,
           SUM(gross_revenue) AS gross_revenue
    FROM dw.fact_sales
    GROUP BY invoice_date, product_code
), returns AS (
    SELECT invoice_date, product_code,
           SUM(quantity_returned) AS units_returned,
           SUM(returned_amount)   AS returned_amount
    FROM dw.fact_returns
    GROUP BY invoice_date, product_code
)
SELECT COALESCE(s.invoice_date, r.invoice_date),
       COALESCE(s.product_code, r.product_code),
       COALESCE(s.units_sold, 0),
       COALESCE(r.units_returned, 0),
       COALESCE(s.gross_revenue, 0),
       COALESCE(r.returned_amount, 0),
       COALESCE(s.gross_revenue, 0) - COALESCE(r.returned_amount, 0)
FROM sales s
FULL OUTER JOIN returns r
  ON r.invoice_date = s.invoice_date AND r.product_code = s.product_code;
