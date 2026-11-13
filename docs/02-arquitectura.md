# 2. Arquitectura del lab

> Ruta de lectura: [1. Caso de negocio](01-caso-de-negocio.md) → **2. Arquitectura** →
> [3. Implementación técnica](03-implementacion.md) →
> [4. Validación con Athena](04-validacion-athena.md) →
> [5. Cambio en vivo](05-cambio-en-vivo.md)

Laboratorio práctico y corto (≈ 60–90 min) del bootcamp AWS Data Engineer.
Se construye un ETL **batch** serverless que lleva los envíos de un operador de
carga por las capas **bronze → silver → gold** con **AWS Glue** (jobs,
crawlers y Data Catalog) y **Amazon S3**. Lo orquestan **EventBridge + Step
Functions** cuando llega el archivo, y se despliega con **Terraform**.

## 2.1 Qué vas a lograr

Al terminar el lab podrás:

1. Generar el CSV diario de envíos con un script de Python y subirlo a `bronze/`.
2. Ver cómo esa subida dispara sola el pipeline (EventBridge → Step Functions)
   y seguir cada paso en el grafo de la ejecución.
3. Obtener Parquet limpio en `silver/` e indicadores por ruta en `gold/`.
4. Consultar las tablas `silver_envios` y `gold_desempeno_rutas` en el Data
   Catalog, registradas por los crawlers, y validarlas con Athena.
5. Entender cómo se hace un cambio de esquema con un agente de IA: SQL +
   contrato → reproceso → catálogo actualizado.

## 2.2 Diagrama

```
 ┌────────────────────────┐
 │ generate_envios_csv.py │  (local, Python stdlib)   ← simula el export del TMS
 └───────────┬────────────┘
             │ upload CSV a bronze/envios/
             ▼
   S3 "Object Created" ─► EventBridge (regla: prefijo bronze/envios/) ─► Step Functions
                                                                          │
     BronzeToSilver ─► silver-crawler ─► SilverToGold ─► gold-crawler ◄───┘
     (startJobRun.sync)  (ciclo de espera)  (startJobRun.sync)  (ciclo de espera)
             │
             ▼
 ┌──────────────────── S3: <proyecto>-<entorno>-<cuenta>-lake ─────────────────────┐
 │                                                                                │
 │  bronze/envios/ingest_date=YYYY-MM-DD/envios.csv   (crudo, tal cual)           │
 │            │                                                                   │
 │            │  Glue job: bronze_to_silver   (SQL: bronze_to_silver.sql)         │
 │            ▼                                                                   │
 │  silver/envios/*.parquet ───────────► silver-crawler ──► tabla silver_envios   │
 │            │                                                                   │
 │            │  Glue job: silver_to_gold     (SQL: silver_to_gold.sql)           │
 │            ▼                                                                   │
 │  gold/desempeno_rutas/*.parquet ────► gold-crawler ────► tabla gold_desempeno_rutas
 │                                                                                │
 │  scripts/  (código, SQL y contratos de los jobs)   tmp/  (TempDir de Glue)     │
 └────────────────────────────────────────────────────────────────────────────────┘
   Glue Data Catalog: base <proyecto>_<entorno>
   CloudWatch Logs con retención de 7 días (jobs y Step Functions); los crawlers
   escriben en /aws-glue/crawlers, compartido por la cuenta (fuera de Terraform)
   IAM: rol de Glue, rol de Step Functions y rol de EventBridge, cada uno mínimo
```

El diagrama completo, con todos los recursos de Terraform agrupados por
módulo, está en [architecture/arch2.png](architecture/arch2.png) (fuente:
[architecture/architecture.dot](architecture/architecture.dot)).

## 2.3 Decisiones principales

Cada decisión de arquitectura está registrada en una ADR:
[0001](adr/0001-etl-medallion-glue-s3.md) (medallion con Glue y S3),
[0002](adr/0002-data-catalog-con-crawlers.md) (catálogo con crawlers),
[0003](adr/0003-orquestacion-eventbridge-step-functions.md) (orquestación).

| Tema | Decisión | Motivo |
|---|---|---|
| Almacenamiento | 1 bucket, 3 prefijos, versionado deshabilitado | Simple de crear, asegurar y destruir |
| Cómputo | Glue Spark 5.1, 2 workers G.1X, timeout 10 min | Serverless y mínimo costo |
| Catálogo | 2 crawlers (silver, gold), `UPDATE_IN_DATABASE` | Descubren el esquema y lo actualizan cuando cambia |
| Esquema esperado | Contratos JSON en `src/contracts/`; los jobs validan sus columnas contra ellos | El cambio de esquema es explícito y revisable en un diff |
| Orquestación | S3 → EventBridge (filtro `bronze/envios/`) → Step Functions Standard | Pipeline event-driven, con grafo visible y `Retry`/`Catch` explícitos |
| Transformaciones | SQL en `src/transformations/`, ejecutado con `spark.sql` | Lógica de negocio separada del Python |
| Formato | CSV en bronze, Parquet en silver y gold | Muestra el valor de un formato columnar |
| Particionado | Ninguno en silver y gold | Volumen pequeño; reproceso simple con `overwrite` |
| IaC | Terraform, un módulo por servicio en `infra/modules/` | Reproducible y fácil de destruir |

## 2.4 Datos de entrada

El script `scripts/generate_envios_csv.py` simula el export diario del TMS
(solo stdlib: `csv`, `random`, `datetime`). Recibe el número de filas, la fecha
(o un rango de fechas) y una semilla: cada fecha genera datos distintos, pero
todos los alumnos obtienen los mismos. Columnas y reglas en
[1. Caso de negocio § 3](01-caso-de-negocio.md#3-dato-fuente-bronze).

Introduce "suciedad" controlada para que silver tenga trabajo visible:
duplicados, IDs vacíos, espacios y mayúsculas inconsistentes, y entregas
tardías para que el OTD no sea 100 %.

## 2.5 El pipeline paso a paso

Al subir un CSV a `bronze/envios/`, EventBridge inicia una ejecución de
`<prefijo>-pipeline`, que recorre estos pasos en orden. Si alguno falla, la
ejecución termina en `PipelineFailed` con el error en `$.error`.

| Paso | Recurso | Qué hace |
|---|---|---|
| 1 | Job `bronze_to_silver` | Lee el CSV, limpia, castea y deduplica por `envio_id` (`bronze_to_silver.sql`); valida contra `silver_envios.json`; escribe Parquet en `silver/envios/` |
| 2 | `silver-crawler` | Crea o actualiza la tabla `silver_envios` |
| 3 | Job `silver_to_gold` | Agrega por fecha y ruta, y calcula OTD, tránsito, volumen e ingreso (`silver_to_gold.sql`); valida contra `gold_desempeno_rutas.json`; escribe en `gold/desempeno_rutas/` |
| 4 | `gold-crawler` | Crea o actualiza la tabla `gold_desempeno_rutas` |

Una ejecución completa tarda entre **8 y 13 minutos** (medido): la primera del
día suele ser la más lenta por el arranque en frío de Glue.

## 2.6 Costos y limpieza

* **Glue jobs:** se cobran por DPU-hora; con 2 workers G.1X, cada job tarda
  ~2–6 min.
* **Crawlers:** se cobran por DPU-hora con un **mínimo facturable por corrida**
  (confirmar en la página de precios); por eso no tienen schedule.
* **Data Catalog:** 1 base y 2 tablas entran en la capa gratuita (confirmar en
  la página de precios).
* **EventBridge:** los eventos de servicios de AWS no tienen costo. **Step
  Functions** Standard cobra por transición de estado; una ejecución tiene unas
  decenas de transiciones.
* **Athena:** cobra por datos escaneados; con estos Parquet, centavos.
* **S3 y CloudWatch Logs** (7 días): despreciables a este volumen.

Al terminar: `terraform -chdir=infra destroy`. El bucket tiene versionado
deshabilitado y `force_destroy = true`, así que se eliminan datos, crawlers,
tablas, jobs y orquestación.
