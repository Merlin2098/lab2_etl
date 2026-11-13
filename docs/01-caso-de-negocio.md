# 1. Caso de negocio — Andes Freight (empresa ficticia)

> Ruta de lectura: **1. Caso de negocio** → [2. Arquitectura](02-arquitectura.md) →
> [3. Implementación técnica](03-implementacion.md) →
> [4. Validación con Athena](04-validacion-athena.md) →
> [5. Cambio en vivo](05-cambio-en-vivo.md)

## 1. La empresa

**Andes Freight** es un operador de carga terrestre (ficticio) con base en
Lima. Mueve carga consolidada y dedicada entre las principales ciudades del
Perú para clientes industriales y de retail.

| Dato | Valor |
|---|---|
| Rutas | Lima ↔ Arequipa, Trujillo, Chiclayo, Piura, Cusco |
| Tipos de carga | `GENERAL`, `REFRIGERADA`, `PELIGROSA` |
| Moneda | Soles (PEN) |
| Volumen | ~1 000 envíos por día |
| Sistema fuente | TMS (Transport Management System), que exporta un CSV diario de envíos |

## 2. El problema

Hoy la gerencia de operaciones arma sus reportes a mano en Excel a partir del
CSV del TMS. Cada reporte toma horas, los números no cuadran entre áreas y
nadie confía en el indicador de puntualidad.

La empresa quiere una capa analítica confiable y automatizada que responda, con
datos del día anterior:

1. ¿Qué rutas cumplen el compromiso de entrega? (**OTD**, On-Time Delivery)
2. ¿Cuántos días tarda en promedio cada ruta?
3. ¿Cuánto volumen (envíos y kg) movemos por ruta y día?
4. ¿Cuánto ingreso genera cada ruta y cuánto por kg transportado?

## 3. Dato fuente (bronze)

Exportación diaria del TMS: `envios_<fecha>.csv`, con una fila por envío. Es
**dato crudo**, por eso trae problemas típicos: envíos duplicados por
reenvío del archivo, IDs vacíos, espacios y mayúsculas inconsistentes, y
fechas de entrega vacías para envíos aún en tránsito.

| Columna | Descripción |
|---|---|
| `envio_id` | Identificador del envío (guía de remisión) |
| `cliente_id` | Cliente que contrata el servicio |
| `fecha_despacho` | Fecha en que el camión sale del origen |
| `fecha_entrega_prometida` | Fecha comprometida con el cliente |
| `fecha_entrega` | Fecha real de entrega (vacía si no se entregó) |
| `origen` / `destino` | Ciudades de la ruta |
| `tipo_carga` | `GENERAL`, `REFRIGERADA` o `PELIGROSA` |
| `peso_kg` | Peso facturable |
| `tarifa_pen` | Monto facturado al cliente |
| `estado` | `ENTREGADO`, `EN_TRANSITO` o `CANCELADO` |

## 4. Capa silver — `silver_envios`

Una fila por envío **único y válido**, con tipos correctos y texto normalizado.
Es la "fuente de verdad" de envíos. Su esquema formal está en
[`src/contracts/silver_envios.json`](../src/contracts/silver_envios.json).

| Columna | Tipo | Regla |
|---|---|---|
| `envio_id` | string | Sin vacíos; deduplicado (se queda el primer registro) |
| `cliente_id` | string | `trim` |
| `fecha_despacho` | date | |
| `fecha_entrega_prometida` | date | |
| `fecha_entrega` | date | Nulo si no se entregó |
| `origen` | string | `initcap(trim(...))` |
| `destino` | string | `initcap(trim(...))` |
| `tipo_carga` | string | `upper(trim(...))` |
| `peso_kg` | decimal(10,2) | |
| `tarifa_pen` | decimal(12,2) | |
| `estado` | string | `upper(trim(...))` |

## 5. Capa gold — `gold_desempeno_rutas` (esquema analítico)

**Granularidad:** una fila por **fecha de despacho × origen × destino**.
**Alcance:** se excluyen los envíos `CANCELADO`.
Esquema formal: [`src/contracts/gold_desempeno_rutas.json`](../src/contracts/gold_desempeno_rutas.json).

| Columna | Tipo | Definición |
|---|---|---|
| `fecha_despacho` | date | Dimensión |
| `origen` | string | Dimensión |
| `destino` | string | Dimensión |
| `envios_total` | bigint | Envíos no cancelados |
| `envios_entregados` | bigint | Envíos con `estado = 'ENTREGADO'` |
| `envios_a_tiempo` | bigint | Entregados con `fecha_entrega <= fecha_entrega_prometida` |
| `otd_pct` | decimal(5,2) | `envios_a_tiempo / envios_entregados × 100` (nulo si no hay entregados) |
| `dias_transito_prom` | decimal(6,2) | Promedio de `fecha_entrega − fecha_despacho` en días, sólo entregados |
| `peso_total_kg` | decimal(14,2) | Suma de `peso_kg` |
| `ingreso_total_pen` | decimal(14,2) | Suma de `tarifa_pen` |
| `ingreso_por_kg_pen` | decimal(10,4) | `ingreso_total_pen / peso_total_kg` |

Cómo responde a las preguntas del negocio:

| Pregunta | Columnas |
|---|---|
| 1. Puntualidad por ruta | `otd_pct` (meta del negocio: ≥ 95 %) |
| 2. Tiempo de tránsito | `dias_transito_prom` |
| 3. Volumen | `envios_total`, `peso_total_kg` |
| 4. Ingreso | `ingreso_total_pen`, `ingreso_por_kg_pen` |

Ejemplo de consulta de un analista (vía Data Catalog):

```sql
select origen, destino,
       sum(envios_a_tiempo) * 100.0 / sum(envios_entregados) as otd_pct
from gold_desempeno_rutas
group by origen, destino
order by otd_pct;
```

Las tablas `silver_envios` y `gold_desempeno_rutas` las registra en el Glue Data
Catalog un crawler por capa. Los contratos definen el esquema **esperado** y
los jobs lo validan antes de escribir.

## 6. Evolución prevista: el cambio en vivo

Operaciones necesita vigilar la **cadena de frío**: el OTD agregado por ruta
esconde que la carga `REFRIGERADA` llega tarde más seguido. Pide los
indicadores de gold **separados por `tipo_carga`**. Eso cambia el esquema y la
granularidad de `gold_desempeno_rutas` (fecha × ruta × tipo de carga) y obliga a
reprocesar gold y volver a ejecutar su crawler. El guion está en
[05-cambio-en-vivo.md](05-cambio-en-vivo.md).

Evolución futura (fuera de la demo): el TMS exportará `costo_operativo_pen`
para medir el **margen por ruta**.

## 7. Glosario

| Término | Significado |
|---|---|
| OTD (On-Time Delivery) | % de envíos entregados en o antes de la fecha prometida |
| Tiempo de tránsito | Días entre el despacho y la entrega |
| TMS | Sistema que gestiona envíos, rutas y flota |
| Guía de remisión | Documento que acompaña la carga; aquí, `envio_id` |
