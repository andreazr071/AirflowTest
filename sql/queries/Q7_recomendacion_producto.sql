-- Q7. Recomendación para el equipo de producto: consultas que respaldan los números.
-- Texto de la recomendación: docs/RECOMENDACION_PRODUCTO.md

-- Q7a. Códigos de mercancía con descripción en conflicto DENTRO de las ventas vs ruido de ajustes.
WITH v AS (
    SELECT p.product_code,
           count(*) FILTER (WHERE d.sale_occurrences > 0) AS nombres_en_ventas,
           count(*)                                       AS textos_total
    FROM dw.dim_product p
    JOIN dw.product_description_variant d USING (product_code)
    WHERE p.is_merchandise
    GROUP BY p.product_code
), rev AS (
    SELECT product_code, sum(gross_revenue) AS bruto FROM dw.agg_daily_product_net GROUP BY product_code
)
SELECT count(*)                                                             AS codigos_mercancia,
       count(*) FILTER (WHERE textos_total > 1)                             AS con_mas_de_un_texto,
       count(*) FILTER (WHERE nombres_en_ventas > 1)                        AS conflicto_de_nombre_en_ventas,
       count(*) FILTER (WHERE textos_total > 1 AND nombres_en_ventas <= 1)  AS solo_ruido_de_ajustes,
       round(100 * sum(bruto) FILTER (WHERE nombres_en_ventas > 1) / sum(bruto), 2) AS pct_revenue_con_conflicto
FROM v JOIN rev USING (product_code);

-- Q7b. Concentración: cuántas referencias hacen el 80 % del revenue neto de mercancía.
WITH t AS (
    SELECT a.product_code, sum(a.net_revenue) AS neto
    FROM dw.agg_daily_product_net a JOIN dw.dim_product p USING (product_code)
    WHERE p.is_merchandise GROUP BY a.product_code
), r AS (
    SELECT neto, sum(neto) OVER (ORDER BY neto DESC) AS acum, sum(neto) OVER () AS total,
           row_number() OVER (ORDER BY neto DESC) AS n, count(*) OVER () AS productos
    FROM t
)
SELECT max(productos) AS productos,
       min(n) FILTER (WHERE acum / total >= 0.8) AS referencias_para_80pct,
       round(100.0 * min(n) FILTER (WHERE acum / total >= 0.8) / max(productos), 1) AS pct_catalogo_para_80pct,
       round(100 * max(acum) FILTER (WHERE n = 10) / max(total), 1) AS pct_top10
FROM r;

-- Q7c. Referencias que generan pérdida neta (devuelto > vendido) y su monto.
SELECT count(*) AS referencias_neto_negativo, round(sum(neto), 2) AS suma_neto_negativo
FROM (SELECT a.product_code, sum(a.net_revenue) AS neto
      FROM dw.agg_daily_product_net a JOIN dw.dim_product p USING (product_code)
      WHERE p.is_merchandise GROUP BY a.product_code HAVING sum(a.net_revenue) < 0) x;

-- Q7d. Un solo pedido explica casi toda la "alta devolución" de Papelería.
SELECT round(100 * (SELECT sum(returned_amount) FROM dw.fact_returns WHERE product_code = '23843')
             / (SELECT sum(r.returned_amount) FROM dw.fact_returns r JOIN dw.dim_product p USING (product_code)
                WHERE p.category = 'Papelería'), 1) AS pct_devuelto_papeleria_por_el_pedido_23843;
