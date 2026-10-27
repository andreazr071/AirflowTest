-- Q6a. ¿Cuántos códigos únicos de producto existen en total? (ya normalizados: mayúsculas, sin espacios)
SELECT count(*)                                         AS codigos_unicos_total,
       count(*) FILTER (WHERE code_pattern = 'CATALOGO')    AS patron_catalogo,
       count(*) FILTER (WHERE code_pattern = 'ALTERNO')     AS patron_alterno_mercancia,
       count(*) FILTER (WHERE code_pattern = 'NO_PRODUCTO') AS no_producto,
       count(*) FILTER (WHERE has_inconsistent_description) AS con_descripcion_inconsistente
FROM dw.dim_product;

-- Q6b. Productos con descripción NO consistente: más de un texto distinto una vez normalizado
-- (mayúsculas/minúsculas y espacios ya NO cuentan como variante). Se listan los 15 de mayor revenue.
SELECT p.product_code,
       p.product_name                                                AS nombre_canonico,
       p.n_description_variants_raw                                  AS variantes_tal_cual,
       p.n_description_variants_norm                                 AS variantes_normalizadas,
       round(sum(a.gross_revenue), 2)                                AS revenue_bruto,
       (SELECT string_agg(v.description_norm || ' (' || v.occurrences || ')', ' | ' ORDER BY v.occurrences DESC)
          FROM dw.product_description_variant v WHERE v.product_code = p.product_code) AS textos_y_apariciones
FROM dw.dim_product p
JOIN dw.agg_daily_product_net a USING (product_code)
WHERE p.has_inconsistent_description
GROUP BY p.product_code, p.product_name, p.n_description_variants_raw, p.n_description_variants_norm
ORDER BY revenue_bruto DESC
LIMIT 15;

-- Q6c. Peso de las descripciones inconsistentes sobre el revenue.
SELECT p.has_inconsistent_description                                   AS descripcion_inconsistente,
       count(DISTINCT p.product_code)                                   AS productos,
       round(100 * sum(a.gross_revenue) / sum(sum(a.gross_revenue)) OVER (), 2) AS pct_revenue
FROM dw.dim_product p
JOIN dw.agg_daily_product_net a USING (product_code)
WHERE p.is_merchandise
GROUP BY 1
ORDER BY 1;
