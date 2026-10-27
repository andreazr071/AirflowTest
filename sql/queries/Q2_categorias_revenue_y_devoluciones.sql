-- Q2. ¿Qué categorías generaron más revenue bruto y cuáles tuvieron mayor proporción de devoluciones?
-- Proporción de devoluciones = monto devuelto / revenue bruto de la categoría.
-- "No producto" (fletes, comisiones...) y "Sin clasificar" se dejan visibles para que sumen el 100 %.
SELECT p.category                                                         AS categoria,
       round(sum(a.gross_revenue), 2)                                     AS revenue_bruto,
       round(100 * sum(a.gross_revenue) / sum(sum(a.gross_revenue)) OVER (), 2) AS pct_del_revenue_total,
       round(sum(a.returned_amount), 2)                                   AS monto_devuelto,
       round(100 * sum(a.returned_amount) / NULLIF(sum(a.gross_revenue), 0), 2) AS pct_devolucion,
       sum(a.units_sold)                                                  AS unidades_vendidas,
       sum(a.units_returned)                                              AS unidades_devueltas
FROM dw.agg_daily_product_net a
JOIN dw.dim_product p USING (product_code)
GROUP BY p.category
ORDER BY revenue_bruto DESC;

-- Q2b. Qué tan confiable es la categoría: peso del revenue según cómo se asignó.
-- (regla = coincidió una palabra clave; default = cayó en "Hogar" por defecto)
SELECT split_part(p.category_source, ':', 1)                              AS origen_categoria,
       count(DISTINCT p.product_code)                                     AS productos,
       round(100 * sum(a.gross_revenue) / sum(sum(a.gross_revenue)) OVER (), 2) AS pct_revenue
FROM dw.agg_daily_product_net a
JOIN dw.dim_product p USING (product_code)
GROUP BY 1
ORDER BY pct_revenue DESC;
