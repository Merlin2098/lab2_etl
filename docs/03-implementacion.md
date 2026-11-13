# 3. Implementación técnica

> Ruta de lectura: [1. Caso de negocio](01-caso-de-negocio.md) →
> [2. Arquitectura](02-arquitectura.md) → **3. Implementación técnica** →
> [4. Validación con Athena](04-validacion-athena.md) →
> [5. Cambio en vivo](05-cambio-en-vivo.md)

Cómo está construido lo descrito en [2. Arquitectura](02-arquitectura.md):
Terraform, parámetros de Glue, SQL, generador de datos y tests. Es la
referencia para leer el código o modificarlo. Los datos de AWS se verificaron
contra la documentación oficial el 2026-11-10 (enlaces al final), y los
hallazgos del primer despliegue están documentados en la sección 2.4.

## 1. Hallazgos de la documentación que afectan el diseño

| Tema | Qué dice AWS | Consecuencia para el lab |
|---|---|---|
| Versión de Glue | 5.1 es la versión **por defecto** (Spark 3.5.6, Python 3.11). 6.0 (Spark 4.1.1, Python 3.13) cambia el comportamiento de `getResolvedOptions` y elimina EMRFS | Usar **`glue_version = "5.1"`** |
| Logs en Glue 5.x | Escribe en `/aws-glue/jobs/error` y `/aws-glue/jobs/output`. Con `--custom-logGroup-prefix=<p>` usa `<p>/error` y `<p>/output` | Terraform crea **2 log groups** con retención y pasa el prefijo al job |
| `--TempDir` | Si no se define, Glue crea un bucket temporal que **puede permitir acceso público** | `--TempDir = s3://<bucket>/tmp/` |
| Timeout | Por defecto 480 min en Glue 5.x | `timeout = 10` |
| Bookmarks | `--job-bookmark-option` controla el procesamiento incremental | `job-bookmark-disable`: cada corrida reprocesa todo |
| Archivos auxiliares | `--extra-files` copia archivos de S3 al directorio de trabajo del driver | El `.sql` y el contrato `.json` viajan así |
| Parámetros propios | Se leen con `getResolvedOptions(sys.argv, [...])`; no usar `--JOB_NAME`, `--mode`, `--debug` | Parámetros del lab: `--bucket`, `--sql_file`, `--contract_file` |
| Permisos S3 | Origen: `s3:ListBucket`, `s3:GetObject`. Destino: además `s3:PutObject`, `s3:DeleteObject` | Policy inline acotada al bucket |
| Capacidad | G.1X = 1 DPU (4 vCPU, 16 GB). *Flex* disponible para G.1X | 2 × G.1X, ejecución `STANDARD` |
| Crawlers: nombre de tabla | Sale de la carpeta. Si el target es una carpeta padre con subcarpetas de esquema parecido, crea **una** tabla con particiones; AWS recomienda una ruta de inclusión por tabla | Un crawler por capa con target en la carpeta raíz de la tabla y `table_prefix` (`silver_`, `gold_`) |
| Crawlers: logs | Escriben siempre en `/aws-glue/crawlers` (compartido por la cuenta, un stream por crawler); solo cambia con una security configuration con KMS. **Hallazgo del primer `apply`**: ya existía y Terraform falló al crearlo | No se gestiona con Terraform (ver 2.4) |
| Crawlers: cambios de esquema | `SchemaChangePolicy.UpdateBehavior`: `LOG` o `UPDATE_IN_DATABASE`; `DeleteBehavior`: `LOG`, `DELETE_FROM_DATABASE` o `DEPRECATE_IN_DATABASE` | `UPDATE_IN_DATABASE` + `LOG` |
| Step Functions + Glue | La integración optimizada de Glue solo cubre `StartJobRun`, con patrón `.sync` (permisos: `StartJobRun`, `GetJobRun`, `GetJobRuns`, `BatchStopJobRun`) | Jobs con `glue:startJobRun.sync`; crawlers con `aws-sdk:glue:startCrawler` + ciclo `Wait → GetCrawler → Choice` |
| Eventos de S3 | Glue no garantiza la entrega ni deduplica los eventos de EventBridge; el consumidor debe ser idempotente | Los jobs sobrescriben (`overwrite`): reprocesar es seguro |

## 2. Terraform: un módulo por servicio

```
infra/
  providers.tf  variables.tf  main.tf  outputs.tf   # raíz: locals (nombres, tags) + llamadas a módulos
  modules/
    s3/            bucket lake, versionado Disabled, block public access, cifrado,
                   notificación a EventBridge, objetos scripts/
    iam/           rol de Glue + AWSGlueServiceRole + policy inline del bucket
    cloudwatch/    log groups de jobs y Step Functions (crawlers: ver 2.4)
    glue/          jobs.tf (2 aws_glue_job) + catalog.tf (database + 2 crawlers)
    stepfunctions/ máquina de estados del pipeline + su rol IAM
    eventbridge/   regla "Object Created" en bronze/envios/ + target + su rol IAM
```

Cada módulo tiene `main.tf` (o archivos temáticos), `variables.tf` y
`outputs.tf`, y recibe `name_prefix` y `tags` desde la raíz. La raíz no declara
recursos.

El Data Catalog es parte del servicio AWS Glue, por eso vive en el módulo
`glue` (archivo `catalog.tf`) y no en un módulo aparte.

Flujo de dependencias (sin ciclos):

```
s3 ──bucket_name, bucket_arn──► iam ──role_arn──► glue
s3 ──bucket_name───────────────────────────────►  glue
cloudwatch ──log_group_prefix──────────────────►  glue
glue ──job/crawler names y ARNs──► stepfunctions ◄──pipeline_log_group_arn── cloudwatch
stepfunctions ──state_machine_arn──► eventbridge ◄──bucket_name── s3
```

| Módulo | Recursos | Entradas clave | Salidas |
|---|---|---|---|
| `s3` | `aws_s3_bucket` (sufijo `lake`, `force_destroy = true`), `aws_s3_bucket_versioning` (`Disabled`), public access block, cifrado SSE-S3, `aws_s3_object` por cada `.py`, `.sql` y contrato `.json` (`etag = filemd5(...)`) | `name_prefix`, `tags`, ruta a `src/` | `bucket_name`, `resource_arn` |
| `iam` | `aws_iam_role` (assume `glue.amazonaws.com`), `AWSGlueServiceRole`, `aws_iam_role_policy` (`s3:ListBucket` en el bucket; `Get/Put/DeleteObject` en `bucket/*`) | `bucket_arn` | `role_arn`, `resource_arn` |
| `cloudwatch` | 2 × `aws_cloudwatch_log_group` de jobs (`/aws-glue/<prefijo>/error` y `/output`) + log group de Step Functions, con `retention_in_days`. El de los crawlers no se gestiona (ver 2.4) | `name_prefix`, `retention_days` | `log_group_prefix`, `log_group_name`, `log_group_arn`, `resource_arn` |
| `glue` | 2 × `aws_glue_job`, `aws_glue_catalog_database`, 2 × `aws_glue_crawler` | `role_arn`, `bucket_name`, `log_group_prefix`, capacidad | nombres y ARN de jobs y crawlers, `database_name`, `resource_arn` |
| `stepfunctions` | `aws_sfn_state_machine` (Standard, logging `ALL`), rol `states.amazonaws.com` + policy | nombres y ARN de jobs y crawlers, `log_group_arn`, `crawler_poll_seconds`, `pipeline_timeout_seconds` | `state_machine_arn`, `state_machine_name`, `resource_arn` |
| `eventbridge` | `aws_cloudwatch_event_rule`, `aws_cloudwatch_event_target`, rol `events.amazonaws.com` + policy | `bucket_name`, `trigger_prefix`, `state_machine_arn`, `enabled` | `rule_name`, `resource_arn` |

Reglas de IAM entre módulos:

* El permiso sobre el bucket va en `iam`, que recibe `bucket_arn`. Jobs y
  crawlers usan **el mismo rol**: `AWSGlueServiceRole` cubre el catálogo y los
  logs (`/aws-glue/*`), y la policy inline cubre el bucket. Los jobs no
  escriben en el catálogo; eso lo hacen los crawlers.
* El rol de Step Functions vive en `stepfunctions`, donde llegan los ARN de
  jobs y crawlers, y solo actúa sobre ellos. Única excepción: las acciones de
  entrega de logs (`logs:CreateLogDelivery`, etc.) exigen `Resource "*"`.
* El rol de EventBridge vive en `eventbridge` y solo puede hacer
  `states:StartExecution` sobre la máquina del pipeline.

### 2.1 S3: versionado deshabilitado

```hcl
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Disabled"
  }
}
```

`Disabled` solo es válido en un bucket que nunca tuvo versionado, y este bucket
es nuevo. No se usa `Suspended`, que corresponde a un bucket que ya tuvo
versionado.

### 2.2 Data Catalog con crawlers (`modules/glue/catalog.tf`)

Terraform crea la base y los crawlers; las **tablas las crean y actualizan los
crawlers** y no forman parte del estado de Terraform.

```hcl
resource "aws_glue_catalog_database" "lake" {
  name = replace(var.name_prefix, "-", "_")
}

locals {
  crawlers = {
    silver = "silver/envios/"         # → tabla silver_envios
    gold   = "gold/desempeno_rutas/"  # → tabla gold_desempeno_rutas
  }
}

resource "aws_glue_crawler" "layer" {
  for_each      = local.crawlers
  name          = "${var.name_prefix}-${each.key}-crawler"
  role          = var.role_arn
  database_name = aws_glue_catalog_database.lake.name
  table_prefix  = "${each.key}_"

  s3_target {
    path       = "s3://${var.bucket_name}/${each.value}"
    exclusions = ["**_SUCCESS"]   # marcador de Spark; no es dato
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  tags = var.tags
}
```

* El target apunta a la **carpeta raíz de cada tabla** (una ruta por tabla),
  así el nombre sale de la carpeta (`envios`, `desempeno_rutas`) más el
  `table_prefix`.
* Sin `schedule`: los ejecuta Step Functions después de cada job.
* Al cambiar el esquema del Parquet, el crawler actualiza la tabla y Glue
  guarda la versión anterior en el historial de la tabla (visible en consola y
  con `get-table-versions`).
* `terraform destroy` borra la base de datos y, con ella, las tablas que
  crearon los crawlers.
* Bronze no se cataloga: es el CSV crudo y solo lo lee `bronze_to_silver` por
  ruta.

Los contratos de `src/contracts/` no generan el catálogo. Definen el esquema
**esperado**: los jobs validan contra ellos antes de escribir (sección 4) y
`tests/aws/` compara la tabla del crawler con el contrato.

Verificado en la primera ejecución E2E (2026-11-12): en Glue 5.1 los jobs
escriben solo archivos `part-*.snappy.parquet` (no aparece `_SUCCESS`), y el
catálogo tiene exactamente 2 tablas (`silver_envios`, `gold_desempeno_rutas`).
La exclusión `**_SUCCESS` se mantiene como protección.

### 2.3 Orquestación (`modules/stepfunctions`, `modules/eventbridge`)

**Disparo.** El bucket envía sus eventos a EventBridge
(`aws_s3_bucket_notification` con `eventbridge = true`). La regla filtra:

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": { "name": ["<bucket>"] },
    "object": { "key": [{ "prefix": "bronze/envios/" }] }
  }
}
```

El filtro por prefijo es obligatorio: sin él, las escrituras de los jobs en
`silver/` y `gold/` dispararían el pipeline en un ciclo infinito. La regla se
desactiva con `enable_event_trigger = false`.

**Máquina de estados** (definida en HCL con `jsonencode`):

```
BronzeToSilver (glue:startJobRun.sync)
  → StartSilverCrawler → WaitSilverCrawler → GetSilverCrawler → IsSilverCrawlerReady
        ↑______________ no READY ______________________________|
                                                   READY → DidSilverCrawlerSucceed
  → SilverToGold (glue:startJobRun.sync)
  → StartGoldCrawler → … (mismo ciclo) … → PipelineSucceeded
Cualquier error (Catch States.ALL) → PipelineFailed, con el detalle en $.error
```

* Los 4 estados de cada crawler se generan con un `for` sobre
  `{ Silver = "SilverToGold", Gold = "PipelineSucceeded" }`.
* `DidXCrawlerSucceed` primero comprueba que exista `LastCrawl.Status`; si no
  existe (el primer crawl aún no se registró), vuelve a esperar.
* `Retry` en los jobs ante `Glue.ConcurrentRunsExceededException` (dos
  archivos seguidos), y en `StartCrawler` ante `Glue.CrawlerRunningException`.
* `TimeoutSeconds = pipeline_timeout_seconds` (1800) corta cualquier ciclo
  colgado.
* Logs en `/aws/vendedlogs/states/<prefijo>-pipeline` (nivel `ALL`, incluye los
  datos de la ejecución), creado en el módulo `cloudwatch`.

### 2.4 Hallazgo: el log group de los crawlers queda fuera de Terraform

**Qué pasó.** La primera versión del módulo `cloudwatch` declaraba
`/aws-glue/crawlers` con retención, como exige la regla "todo log group en
Terraform". El primer `terraform apply` en una cuenta real falló con:

```
Error: creating CloudWatch Logs Log Group (/aws-glue/crawlers): ...
ResourceAlreadyExistsException: The specified log group already exists
```

**Por qué.**

* Los crawlers **no admiten un log group propio**: Glue los hace escribir siempre
  en `/aws-glue/crawlers`, un log group **compartido por toda la cuenta y
  región**, que el servicio crea la primera vez que corre cualquier crawler.
  Los jobs sí admiten prefijo propio (`--custom-logGroup-prefix`); los
  crawlers no.
* La única forma de sacar a un crawler de ese log group es adjuntarle una
  *security configuration* con cifrado de CloudWatch Logs por KMS. Glue usa
  entonces un log group cuyo nombre incluye la configuración y el rol. Eso
  exige una clave KMS de pago, una key policy para CloudWatch Logs y
  `logs:AssociateKmsKey` en el rol: demasiado para este lab.

**Decisión.** El log group de los crawlers **no se gestiona con Terraform**: no
se crea ni se importa al estado. Si Terraform lo administrara, `terraform
destroy` borraría también los logs de otros proyectos de la cuenta.

**Consecuencias.**

* Es la única excepción a la regla de log groups en Terraform (ver AGENTS.md).
* Los logs del lab siguen separados: cada crawler escribe en **su propio log
  stream**, con el nombre del crawler (`<prefijo>-silver-crawler`,
  `<prefijo>-gold-crawler`). En CloudWatch → `/aws-glue/crawlers`, filtrar los
  streams por `<prefijo>-`.
* El rol de Glue ya puede escribir ahí (`AWSGlueServiceRole` cubre `/aws-glue/*`).
* Glue crea ese log group **sin retención**. Si la cuenta es propia, se fija
  una vez a mano (afecta a todos los crawlers de la cuenta):

```bash
aws logs describe-log-groups --log-group-name-prefix /aws-glue/crawlers \
  --query "logGroups[].{name:logGroupName,retencion:retentionInDays}"
aws logs put-retention-policy --log-group-name /aws-glue/crawlers --retention-in-days 7
```

### 2.5 Lo que se retira del template

`aws_s3_object.artifact_bundle`, las variables `artifact_*` y
`enable_artifact_bucket_versioning`, todo lo del budget (`aws_budgets_budget`,
SNS y variables `enable_budget_guardrail`/`budget_*`), el log group genérico
`/aws/data-jobs/...`, `scripts/package.py`, y `src/config/` (vacío; la
configuración vive en variables de Terraform y argumentos de Glue).

Variables nuevas en la raíz: `glue_version` (`"5.1"`), `glue_worker_type`
(`"G.1X"`), `glue_number_of_workers` (`2`, validado entre 2 y 4),
`glue_timeout_minutes` (`10`, validado entre 1 y 30),
`enable_event_trigger` (`true`),
`crawler_poll_seconds` (`20`), `pipeline_timeout_seconds` (`1800`).

Salidas de la raíz: `lake_bucket_name`, `lake_bucket_arn`, `glue_role_arn`,
`glue_job_names`, `glue_crawler_names`, `glue_database_name`,
`pipeline_state_machine_arn`, `pipeline_trigger_rule`, `log_group_name`,
`log_group_arn`, `code_object_keys`.

## 3. Definición de los Glue jobs (`modules/glue/jobs.tf`)

```hcl
resource "aws_glue_job" "bronze_to_silver" {
  name              = "${var.name_prefix}-bronze-to-silver"
  role_arn          = var.role_arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.bucket_name}/scripts/bronze_to_silver.py"
  }

  default_arguments = {
    "--bucket"                 = var.bucket_name
    "--sql_file"               = "bronze_to_silver.sql"
    "--contract_file"          = "silver_envios.json"
    "--extra-files"            = join(",", [
      "s3://${var.bucket_name}/scripts/sql/bronze_to_silver.sql",
      "s3://${var.bucket_name}/scripts/contracts/silver_envios.json",
    ])
    "--TempDir"                = "s3://${var.bucket_name}/tmp/"
    "--job-bookmark-option"    = "job-bookmark-disable"
    "--custom-logGroup-prefix" = var.log_group_prefix
  }

  tags = var.tags
}
```

`silver_to_gold` es igual, con su script, `silver_to_gold.sql` y
`gold_desempeno_rutas.json`.

## 4. Scripts de Glue (`src/jobs/`)

Esqueleto de `bronze_to_silver.py` (≈ 25 líneas, sólo Spark SQL):

```python
import json
import sys

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession

args = getResolvedOptions(sys.argv, ["bucket", "sql_file", "contract_file"])
spark = SparkSession.builder.getOrCreate()
base = f"s3://{args['bucket']}"

with open(args["contract_file"], encoding="utf-8") as f:
    contract = json.load(f)
with open(args["sql_file"], encoding="utf-8") as f:
    sql = f.read()

spark.read.option("header", True).csv(f"{base}/bronze/envios/") \
    .createOrReplaceTempView("bronze_envios")
result = spark.sql(sql)

# Contrato primero: nombres, orden y tipos deben coincidir antes de escribir.
expected = [(c["name"], c["type"]) for c in contract["columns"]]
if result.dtypes != expected:
    raise ValueError(f"Salida {result.dtypes} no coincide con el contrato {expected}")

result.write.mode("overwrite").parquet(f"{base}/{contract['s3_prefix']}")
```

`silver_to_gold.py` lee `spark.read.parquet(f"{base}/silver/envios/")`, registra
la vista `silver_envios` y escribe en el `s3_prefix` del contrato de gold.

La validación compara nombres, orden y **tipos**: `result.dtypes` de Spark
usa el mismo formato que el contrato (`string`, `date`, `bigint`,
`decimal(10,2)`). Es el "seguro" del cambio en vivo: si alguien cambia el SQL
sin actualizar el contrato (o al revés), el job falla con un mensaje claro y no
escribe datos inconsistentes con el catálogo. `tests/test_contracts.py` hace el
mismo chequeo de nombres y orden en local, sin gastar una corrida de Glue.

## 5. SQL (`src/transformations/`)

`bronze_to_silver.sql`:

```sql
with limpio as (
    select
        trim(envio_id)                              as envio_id,
        trim(cliente_id)                            as cliente_id,
        to_date(fecha_despacho)                     as fecha_despacho,
        to_date(fecha_entrega_prometida)            as fecha_entrega_prometida,
        to_date(nullif(trim(fecha_entrega), ''))    as fecha_entrega,
        initcap(trim(origen))                       as origen,
        initcap(trim(destino))                      as destino,
        upper(trim(tipo_carga))                     as tipo_carga,
        cast(peso_kg as decimal(10, 2))             as peso_kg,
        cast(tarifa_pen as decimal(12, 2))          as tarifa_pen,
        upper(trim(estado))                         as estado,
        row_number() over (
            partition by trim(envio_id) order by fecha_despacho
        )                                           as rn
    from bronze_envios
    where envio_id is not null and trim(envio_id) <> ''
)
select envio_id, cliente_id, fecha_despacho, fecha_entrega_prometida,
       fecha_entrega, origen, destino, tipo_carga, peso_kg, tarifa_pen, estado
from limpio
where rn = 1
```

`silver_to_gold.sql`:

```sql
select
    fecha_despacho,
    origen,
    destino,
    count(*)                                                    as envios_total,
    count_if(estado = 'ENTREGADO')                              as envios_entregados,
    count_if(estado = 'ENTREGADO'
             and fecha_entrega <= fecha_entrega_prometida)      as envios_a_tiempo,
    cast(100.0 * count_if(estado = 'ENTREGADO'
                          and fecha_entrega <= fecha_entrega_prometida)
         / nullif(count_if(estado = 'ENTREGADO'), 0)
         as decimal(5, 2))                                      as otd_pct,
    cast(avg(case when estado = 'ENTREGADO'
                  then datediff(fecha_entrega, fecha_despacho) end)
         as decimal(6, 2))                                      as dias_transito_prom,
    cast(sum(peso_kg) as decimal(14, 2))                        as peso_total_kg,
    cast(sum(tarifa_pen) as decimal(14, 2))                     as ingreso_total_pen,
    cast(sum(tarifa_pen) / nullif(sum(peso_kg), 0)
         as decimal(10, 4))                                     as ingreso_por_kg_pen
from silver_envios
where estado <> 'CANCELADO'
group by fecha_despacho, origen, destino
```

Cada columna termina en un `cast` explícito al tipo del contrato, así el
Parquet coincide con lo que declara el catálogo.

## 6. Generador (`scripts/generate_envios_csv.py`)

* Sólo stdlib (`argparse`, `csv`, `random`, `datetime`) + `boto3` para subir.
* Argumentos: `--rows` (1000), `--date` (hoy), `--days` (14, rango de
  `fecha_despacho` hacia atrás), `--seed` (42), `--out`
  (`data/envios_<fecha>.csv`), `--upload`, `--bucket` (o variable `LAB_BUCKET`,
  salida de `terraform output -raw lake_bucket_name`).
* Reglas realistas:
  * rutas Lima ↔ {Arequipa, Trujillo, Chiclayo, Piura, Cusco}, cada una con su
    tránsito base en días;
  * ~85 % `ENTREGADO`, ~10 % `EN_TRANSITO`, ~5 % `CANCELADO`;
  * ~10 % de entregas tarde, para que el OTD no sea 100 %;
  * tarifa ≈ peso × tarifa por kg de la ruta × recargo por tipo de carga.
* Suciedad controlada: ~3 % `envio_id` duplicados, ~1 % vacíos, espacios y
  mayúsculas mezcladas en `origen`, `destino`, `tipo_carga` y `estado`.
* Destino: `s3://<bucket>/bronze/envios/ingest_date=<fecha>/envios.csv`.
  Si se vuelve a generar la misma fecha, se sobrescribe el lote.
* Credenciales: `.env.credentials` vía `python-dotenv`.

## 7. Tests

| Test | Tipo | Qué valida |
|---|---|---|
| `tests/test_generate_envios_csv.py` | local | Encabezado esperado, nº de filas, semilla reproducible, presencia de duplicados y de envíos tardíos |
| `tests/test_contracts.py` | local | Contratos con `table`, `s3_prefix`, `columns`; tipos válidos de Glue; nombres de columnas presentes en el `select` final de cada SQL |
| `tests/aws/test_lake_infra.py` (`@pytest.mark.cloud`) | boto3 | Bucket privado, cifrado y sin versionado; jobs con `GlueVersion == "5.1"`, `G.1X`, timeout 10; crawlers con `UPDATE_IN_DATABASE`; log groups con retención |
| `tests/aws/test_catalog_vs_contract.py` (`@pytest.mark.cloud`) | boto3 | Tras correr los crawlers: columnas y tipos de cada tabla del catálogo == contrato. Detecta un crawler que no se ejecutó |

`test_contracts.py` es el chequeo rápido del cambio en vivo: si el agente edita
el contrato pero no el SQL (o al revés), falla en local en segundos, antes de
gastar una corrida de Glue.

## 8. Orden de implementación

1. ✅ Terraform: módulos `s3`, `cloudwatch`, `iam`, `glue`, `stepfunctions`,
   `eventbridge` y la raíz. `fmt` e `init` OK; `validate` pendiente (en este
   equipo el provider falla con un error TLS local ajeno al código).
2. ✅ SQL + scripts de Glue (con validación de contrato).
3. ✅ Generador + tests locales (`test_generate_envios_csv.py`, `test_contracts.py`).
4. ✅ Tests `tests/aws/` (`test_lake_infra.py`, `test_catalog_vs_contract.py`),
   con el marcador `cloud`; se ejecutan con `run_cloud_tests.py`.
5. Ensayo completo del cambio en vivo (`tipo_carga` en gold) para medir los
   tiempos reales de una ejecución completa.
6. La persona ejecuta `apply` y sube los datos; el pipeline corre solo:

```bash
python scripts/generate_envios_csv.py --rows 1000 --upload      # dispara el pipeline
aws stepfunctions list-executions --state-machine-arn <arn> --max-items 1
# Ejecución manual (regla desactivada o reintento):
aws stepfunctions start-execution --state-machine-arn <arn>
# Verificación del catálogo:
aws glue get-table          --database-name <base> --name gold_desempeno_rutas
aws glue get-table-versions --database-name <base> --table-name gold_desempeno_rutas
```

## 9. Pendientes por decidir

* **Consulta SQL sobre el catálogo (Athena):** queda fuera de alcance. Si se
  quiere mostrar la consulta del analista del caso de negocio, se necesita un
  workgroup con ubicación de resultados (por ejemplo, `athena-results/` en el
  mismo bucket) en un módulo `athena`.
* **Precio exacto** por DPU-hora de jobs y crawlers (incluido el mínimo
  facturable por corrida de crawler) y del Data Catalog: confirmar en la página
  de precios de la región antes de la sesión.

## Referencias

* Versiones de Glue: https://docs.aws.amazon.com/glue/latest/dg/release-notes.html
* Propiedades de jobs Spark: https://docs.aws.amazon.com/glue/latest/dg/add-job.html
* Parámetros de jobs: https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-glue-arguments.html
* Logging en Glue 5.x: https://docs.aws.amazon.com/glue/latest/dg/monitor-continuous-logging.html
* Permisos S3 del rol: https://docs.aws.amazon.com/glue/latest/dg/getting-started-min-privs-job.html
* Tipos de worker: https://docs.aws.amazon.com/glue/latest/dg/worker-types.html
* Crawlers, tablas y particiones: https://docs.aws.amazon.com/glue/latest/dg/add-crawler.html
* `SchemaChangePolicy`: https://docs.aws.amazon.com/glue/latest/dg/aws-glue-api-crawler-crawling.html
* Step Functions + Glue: https://docs.aws.amazon.com/step-functions/latest/dg/connect-glue.html
* Glue y eventos de EventBridge: https://docs.aws.amazon.com/glue/latest/dg/starting-workflow-eventbridge.html
