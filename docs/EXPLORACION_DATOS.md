# Exploración de las fuentes

Cifras medidas sobre los archivos reales con `scripts/profile_sources.py` y las reglas del pipeline.

## data.csv (carrie1/ecommerce-data), volcado diario
| Aspecto | Hallazgo |
|---|---|
| Estructura | 541.909 filas, 8 columnas (InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country) |
| Codificación | latin-1 (falla en UTF-8 por el símbolo £): el lector reintenta en latin-1 |
| Fechas | formato `M/D/YYYY H:MM`, 2010-12-01 a 2011-12-09, hora local del Reino Unido (sin zona) |
| Cantidad <= 0 | 10.624 filas: 9.288 con factura "C" (devoluciones, precio > 0) y 1.336 sin "C" con precio 0 (ajustes de inventario) |
| Precio | 2.515 en cero (1.181 en ventas, 1.336 en ajustes) y 2 negativos ("Adjust bad debt", facturas A) |
| Sin customer ID | 135.080 filas (24,9 %) |
| Descripción | 1.454 vacías; 3.036 no están en mayúsculas; 4.211 textos crudos vs 4.194 en mayúsculas |
| Códigos | 4.070 crudos -> 3.958 normalizados (1.977 filas traen minúsculas); 32 códigos no siguen `\d{5}[A-Z]{0,2}` (POST, DOT, M, C2, D, S, BANK CHARGES, AMAZONFEE, CRUK, GIFT_*, DCGS*, PADS) |
| Duplicados | 5.268 filas idénticas en todas las columnas |
| Países | 38 (Reino Unido = 91 % de las filas) |

## online_retail_II.csv (Online Retail II, UCI)
1.067.371 filas (2009-12-01 a 2011-12-09), columnas `Invoice`, `Price`, `Customer ID` en lugar de
`InvoiceNo`, `UnitPrice`, `CustomerID`; fechas ISO `YYYY-MM-DD HH:MM:SS`; 34.213 duplicados exactos y
2.750 ventas con precio <= 0. **Compatibilidad:** mismas 8 columnas lógicas, mismo significado y misma zona
horaria local. **Incompatibles:** nombres de columna y formato de fecha (resueltos con alias y formatos por fuente).
Las 535.463 filas válidas de data.csv aparecen también aquí (coinciden en toda la clave compuesta).

## Resultado de la limpieza (carga completa con ambas fuentes)
| Fuente | Leídas | Rechazadas | Motivo |
|---|---|---|---|
| data.csv | 541.909 | 6.446 | 5.265 duplicado exacto, 1.181 precio no positivo en venta |
| online_retail_II.csv | 1.067.371 | 36.963 | 34.213 duplicado exacto, 2.750 precio no positivo en venta |

Descartadas por solapamiento (copia de la fuente de menor prioridad): 535.463. Cargadas: 1.007.912 ventas y 22.496 devoluciones/ajustes.
