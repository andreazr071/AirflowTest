# Guía de visualizaciones Power BI (preguntas de negocio)

Paleta: `#731652` (principal/oscuro), `#D9487D` (ventas), `#D96685` (secundario), `#D9A679` (acento/devoluciones), `#D9D9D9` (neutro).
Convención: **Ventas Brutas = #D9487D, Devoluciones = #D9A679, Ventas Netas = #731652**.

## Medidas nuevas que hay que crear (no están en tu lista)
```DAX
Tasa Devolución Unidades = DIVIDE([Unidades Devueltas], [Unidades Vendidas])
Códigos Únicos = DISTINCTCOUNT(dim_product[product_code])
Productos Descripción Inconsistente = CALCULATE(COUNTROWS(dim_product), dim_product[has_inconsistent_description] = TRUE())
% Revenue Nombre Inconsistente =
    DIVIDE(CALCULATE([Ventas Brutas], dim_product[has_inconsistent_description] = TRUE()), [Ventas Brutas])
% Neto Acumulado =
    VAR actual = [Ventas Netas]
    VAR todos  = ALLSELECTED(dim_product[product_code])
    RETURN DIVIDE(SUMX(FILTER(todos, [Ventas Netas] >= actual), [Ventas Netas]), CALCULATE([Ventas Netas], todos))
```
Ajusta los nombres de tablas y columnas a tu modelo.

## Páginas y visuales por pregunta
| Pregunta | Visual | Datos |
|---|---|---|
| **Q1** Evolución mensual de ventas netas | Gráfico de **columnas agrupadas y líneas** | Eje X: mes (Calendario). Columnas: Ventas Brutas y Ventas Netas. Línea (eje secundario): Var % Ventas Netas MoM. Tarjetas: Ventas Netas, Ventas Brutas, Devoluciones. Segmentador: año |
| **Q2** Categorías con más revenue bruto y más devoluciones | **Barras horizontales** + **dispersión** | Barras: categoría vs Ventas Brutas (etiqueta % del Revenue Total), orden descendente. Dispersión: X = Ventas Brutas, Y = % Devolución, tamaño = Devoluciones, leyenda = categoría. Aviso: ~85 % del revenue cae en Hogar por defecto |
| **Q3a** Top 10 productos por revenue neto | **Barras horizontales** con filtro Top N | Eje: product_name; Valor: Ventas Netas. Filtro del visual: Top 10 por Ventas Netas; filtro de página: is_merchandise = Verdadero |
| **Q3b** Top 10 por tasa de devolución | **Barras horizontales** con filtro Top N | Eje: product_name; Valor: Tasa Devolución Unidades. Filtro: Top 10 por esa medida y Unidades Vendidas ≥ 100 (evita tasas de 100 % con 1 unidad) |
| **Q3 (detalle)** | **Tabla** | product_code, product_name, Ranking Producto, Ventas Netas, Unidades Vendidas, Unidades Devueltas, Tasa Devolución Unidades |
| **Q4** Países y ticket promedio | **Mapa de burbujas** + **columnas y línea** | Mapa: ubicación = país, tamaño = Facturas. Combo: columnas = Facturas (ordenadas), línea = Ticket Promedio. Treemap opcional con % Facturas. El Reino Unido domina: muestra Top 10 países |
| **Q5** Identificados vs anónimos | **Anillo** + **columnas agrupadas** | Anillo: Revenue Identificado vs Revenue Anónimo (% Revenue Anónimo en tarjeta). Columnas: Ticket Identificado y Ticket Anónimo. Tarjetas de Facturas por segmento |
| **Q6** Descripciones inconsistentes y códigos únicos | **Tarjetas** + **tabla** | Tarjetas: Códigos Únicos, Productos Descripción Inconsistente, % Revenue Nombre Inconsistente. Tabla: product_code, nombre canónico, variantes, Ventas Brutas (top 15) |
| **Q7** Recomendación a producto | **Pareto** + **cascada** | Pareto: columnas = Ventas Netas por producto (desc), línea = % Neto Acumulado (marca el 80 %). Cascada: Ventas Brutas → Devoluciones → Ventas Netas. Tarjeta: productos con neto negativo |

## Distribución sugerida
1. **Resumen** — tarjetas (Ventas Brutas, Devoluciones, Ventas Netas, Ticket Promedio, % Devolución) + Q1.
2. **Producto y categoría** — Q2, Q3a, Q3b, Q6.
3. **Geografía y clientes** — Q4, Q5.
4. **Recomendación** — Q7 y texto de `docs/RECOMENDACION_PRODUCTO.md`.

Segmentadores globales: año, país, categoría y `is_merchandise` (para excluir fletes, comisiones y bonos). Logo: `docs/branding/logo_datamart.png`.
