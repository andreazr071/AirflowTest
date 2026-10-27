-- Q4. ¿Qué países concentran la mayor parte de las transacciones y cómo varía el ticket promedio?
-- Transacción = factura de venta (invoice_no distinto en fact_sales).
-- Ticket promedio = revenue bruto de la factura, promediado por país (revenue / nº de facturas).
SELECT c.country_name                                                       AS pais,
       count(DISTINCT s.invoice_no)                                         AS facturas,
       round(100.0 * count(DISTINCT s.invoice_no) / sum(count(DISTINCT s.invoice_no)) OVER (), 2) AS pct_facturas,
       round(sum(s.gross_revenue), 2)                                       AS revenue_bruto,
       round(sum(s.gross_revenue) / count(DISTINCT s.invoice_no), 2)        AS ticket_promedio
FROM dw.fact_sales s
JOIN dw.dim_country c USING (country_id)
GROUP BY c.country_name
ORDER BY facturas DESC;
