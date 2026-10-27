-- Q1. ¿Cuál fue la evolución mensual de las ventas netas (descontando devoluciones)?
-- Neto = revenue bruto - devoluciones/ajustes del mismo producto y día (tabla agg_daily_product_net).
-- Se muestra el total y el neto solo de mercancía (excluye fletes, comisiones, descuentos, bonos).
WITH mensual AS (
    SELECT date_trunc('month', a.invoice_date)::date                       AS mes,
           sum(a.gross_revenue)                                            AS ventas_brutas,
           sum(a.returned_amount)                                          AS devoluciones,
           sum(a.net_revenue)                                              AS ventas_netas,
           sum(a.net_revenue) FILTER (WHERE p.is_merchandise)              AS ventas_netas_solo_mercancia
    FROM dw.agg_daily_product_net a
    JOIN dw.dim_product p USING (product_code)
    GROUP BY 1
)
SELECT mes,
       round(ventas_brutas, 2)                AS ventas_brutas,
       round(devoluciones, 2)                 AS devoluciones,
       round(ventas_netas, 2)                 AS ventas_netas,
       round(ventas_netas_solo_mercancia, 2)  AS ventas_netas_solo_mercancia,
       round(100 * (ventas_netas / NULLIF(lag(ventas_netas) OVER (ORDER BY mes), 0) - 1), 1)
                                              AS variacion_pct_vs_mes_anterior
FROM mensual
ORDER BY mes;
