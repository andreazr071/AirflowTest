-- Q5. ¿Hay diferencia de comportamiento entre clientes identificados y transacciones sin customer ID?
-- (Aplica porque las transacciones sin cliente se CONSERVARON, con customer_id NULL.)
SELECT CASE WHEN s.is_anonymous THEN 'Anónimo (sin customer ID)' ELSE 'Identificado' END AS segmento,
       count(*)                                                        AS lineas,
       count(DISTINCT s.invoice_no)                                    AS facturas,
       round(100 * sum(s.gross_revenue) / sum(sum(s.gross_revenue)) OVER (), 2) AS pct_revenue,
       round(sum(s.gross_revenue) / count(DISTINCT s.invoice_no), 2)   AS ticket_promedio,
       round(count(*)::numeric / count(DISTINCT s.invoice_no), 2)      AS lineas_por_factura,
       round(sum(s.quantity)::numeric / count(DISTINCT s.invoice_no), 1) AS unidades_por_factura,
       round(sum(s.gross_revenue) / sum(s.quantity), 2)                AS precio_promedio_por_unidad
FROM dw.fact_sales s
GROUP BY s.is_anonymous
ORDER BY segmento;

-- Q5b. Devoluciones por segmento (monto devuelto / revenue bruto del segmento).
WITH ventas AS (
    SELECT is_anonymous, sum(gross_revenue) AS bruto FROM dw.fact_sales GROUP BY is_anonymous
), devol AS (
    SELECT is_anonymous, sum(returned_amount) AS devuelto FROM dw.fact_returns GROUP BY is_anonymous
)
SELECT CASE WHEN v.is_anonymous THEN 'Anónimo (sin customer ID)' ELSE 'Identificado' END AS segmento,
       round(v.bruto, 2) AS revenue_bruto, round(COALESCE(d.devuelto, 0), 2) AS monto_devuelto,
       round(100 * COALESCE(d.devuelto, 0) / v.bruto, 2) AS pct_devolucion
FROM ventas v LEFT JOIN devol d USING (is_anonymous)
ORDER BY segmento;
