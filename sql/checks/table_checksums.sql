-- Huella (md5) del contenido de cada tabla, sin columnas volátiles (loaded_at, updated_at).
-- Idempotencia: ejecútala, vuelve a correr el DAG con los mismos archivos y ejecútala de nuevo:
-- las dos salidas deben ser idénticas.
SELECT 'dim_country' AS tabla, count(*) AS filas,
       md5(string_agg(t::text, '|' ORDER BY country_id)) AS huella FROM dw.dim_country t
UNION ALL SELECT 'dim_customer', count(*), md5(string_agg(t::text, '|' ORDER BY customer_id)) FROM dw.dim_customer t
UNION ALL SELECT 'dim_product', count(*), md5(string_agg(t::text, '|' ORDER BY product_code)) FROM dw.dim_product t
UNION ALL SELECT 'product_description_variant', count(*),
       md5(string_agg(t::text, '|' ORDER BY product_code, description_norm)) FROM dw.product_description_variant t
UNION ALL SELECT 'fact_sales', count(*), md5(string_agg(t::text, '|' ORDER BY sale_id)) FROM dw.fact_sales t
UNION ALL SELECT 'fact_returns', count(*), md5(string_agg(t::text, '|' ORDER BY return_id)) FROM dw.fact_returns t
UNION ALL SELECT 'agg_daily_product_net', count(*),
       md5(string_agg(t::text, '|' ORDER BY invoice_date, product_code)) FROM dw.agg_daily_product_net t
UNION ALL SELECT 'rejected_records', count(*),
       md5(string_agg(concat_ws(',', reject_id, source_system, source_row_number, reject_reason, invoice_no,
                                stock_code, description, quantity, invoice_date, unit_price, customer_id, country),
                      '|' ORDER BY reject_id)) FROM dw.rejected_records
UNION ALL SELECT 'etl_run_audit', count(*),
       md5(string_agg(concat_ws(',', logical_date, source_system, metric, value), '|'
                      ORDER BY logical_date, source_system, metric)) FROM dw.etl_run_audit
ORDER BY 1;
