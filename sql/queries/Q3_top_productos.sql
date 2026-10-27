-- Q3a. Los 10 productos (mercancía) con mayor revenue neto.
SELECT a.product_code,
       p.product_name,
       p.category,
       sum(a.units_sold)                       AS unidades_vendidas,
       round(sum(a.gross_revenue), 2)          AS revenue_bruto,
       round(sum(a.net_revenue), 2)            AS revenue_neto
FROM dw.agg_daily_product_net a
JOIN dw.dim_product p USING (product_code)
WHERE p.is_merchandise
GROUP BY a.product_code, p.product_name, p.category
ORDER BY revenue_neto DESC
LIMIT 10;

-- Q3b. Los 10 productos con mayor tasa de devolución (unidades devueltas / unidades vendidas).
-- Para que la tasa signifique algo se exige un volumen mínimo de ventas (parámetro min_unidades):
-- con 1 unidad vendida y 1 devuelta la tasa sería 100 % sin ser una señal real.
-- ATENCIÓN: una tasa > 100 % significa que se devolvió más de lo vendido dentro del periodo cargado
-- (la devolución corresponde a una venta anterior al periodo o registrada con otro código). Es una
-- anomalía de los datos, no un producto "devuelto 30 veces"; por eso se marca en `anomalia` y se
-- ofrece Q3c con las tasas interpretables (<= 100 %).
WITH parametros AS (SELECT 100 AS min_unidades),
totales AS (
    SELECT a.product_code, p.product_name, p.category,
           sum(a.units_sold)     AS unidades_vendidas,
           sum(a.units_returned) AS unidades_devueltas,
           sum(a.net_revenue)    AS revenue_neto
    FROM dw.agg_daily_product_net a
    JOIN dw.dim_product p USING (product_code)
    WHERE p.is_merchandise
    GROUP BY a.product_code, p.product_name, p.category
)
SELECT t.product_code, t.product_name, t.category,
       t.unidades_vendidas, t.unidades_devueltas,
       round(100.0 * t.unidades_devueltas / t.unidades_vendidas, 2) AS tasa_devolucion_pct,
       (t.unidades_devueltas > t.unidades_vendidas)                 AS anomalia_devuelto_mayor_que_vendido,
       round(t.revenue_neto, 2) AS revenue_neto
FROM totales t, parametros pr
WHERE t.unidades_vendidas >= pr.min_unidades
ORDER BY tasa_devolucion_pct DESC, t.unidades_devueltas DESC
LIMIT 10;

-- Q3c. Top 10 de tasa de devolución SOLO entre productos con devoluciones <= ventas (tasa <= 100 %).
WITH parametros AS (SELECT 100 AS min_unidades),
totales AS (
    SELECT a.product_code, p.product_name, p.category,
           sum(a.units_sold)     AS unidades_vendidas,
           sum(a.units_returned) AS unidades_devueltas,
           sum(a.net_revenue)    AS revenue_neto
    FROM dw.agg_daily_product_net a
    JOIN dw.dim_product p USING (product_code)
    WHERE p.is_merchandise
    GROUP BY a.product_code, p.product_name, p.category
)
SELECT t.product_code, t.product_name, t.category,
       t.unidades_vendidas, t.unidades_devueltas,
       round(100.0 * t.unidades_devueltas / t.unidades_vendidas, 2) AS tasa_devolucion_pct,
       round(t.revenue_neto, 2) AS revenue_neto
FROM totales t, parametros pr
WHERE t.unidades_vendidas >= pr.min_unidades
  AND t.unidades_devueltas <= t.unidades_vendidas
ORDER BY tasa_devolucion_pct DESC, t.unidades_devueltas DESC
LIMIT 10;
