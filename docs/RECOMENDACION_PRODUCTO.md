# Recomendación para el equipo de producto (Q7)

Números de `sql/queries/Q7_recomendacion_producto.sql` y Q1 a Q6, sobre la carga con ambas fuentes
(2009-12-01 a 2011-12-09, revenue en GBP).

## Recomendación principal
**Crear un maestro de catálogo con un único nombre comercial por código y un campo aparte para el motivo de ajuste.**

Por qué, con números:
- 1.112 de los 4.754 códigos de mercancía con descripción (23 %) tienen más de un texto distinto.
- En **595 códigos hay nombres en conflicto dentro de las propias ventas** y suman el **26,1 % del revenue bruto**
  (p. ej. `JUMBO BAG RED RETROSPOT` aparece también como `JUMBO BAG RED WHITE SPOTTY`; `DOORMAT RED RETROSPOT`
  con 4 nombres). Un mismo producto se ve distinto según el canal, y cualquier reporte por nombre lo parte en pedazos.
- Los otros 517 códigos solo tienen ruido: el personal escribe motivos ("DAMAGED", "SMASHED", "?") en el campo
  descripción al registrar ajustes. Un campo `motivo_ajuste` los elimina de raíz.

## Hallazgos que acompañan (y qué NO hacer)
1. **Enfocar disponibilidad y calidad en ~1.040 referencias**: el 20,6 % del catálogo (1.038 de 5.051) genera el 80 % del revenue neto
   de mercancía; solo las 10 primeras suman el 7,6 %, así que no hay un "producto estrella" que proteger sino una cola larga.
2. **No hay un problema de referencias que pierden dinero**: solo 23 referencias tienen neto negativo, por −£564 en total.
   La pregunta del negocio ("¿qué referencias generan pérdidas?") se responde: casi ninguna.
3. **No descartar Papelería por su 14 % de devoluciones**: el 85,5 % del monto devuelto de la categoría es un único
   pedido (factura 581483, 80.995 unidades, £168.470, cancelado 12 minutos después). Sin él, la devolución de la
   categoría baja a ~2,3 % (28.631 / 1.235.509). Conviene excluir ese pedido de los análisis de devoluciones.
4. **Capturar el customer ID en el checkout**: el 15 % del revenue viene de compras anónimas, con ticket de £998 frente a £470
   y devoluciones de 12,2 % frente a 6,2 %; hoy no se les puede hacer seguimiento.

## Salvedades
Diciembre 2011 aparece con −70 % porque los datos terminan el día 9. Las categorías son heurísticas (83 % del
revenue cae en "Hogar" por defecto), por eso la recomendación se apoya en productos y no en categorías.
