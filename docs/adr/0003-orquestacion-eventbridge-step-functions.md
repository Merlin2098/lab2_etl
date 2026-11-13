# ADR 0003 — Orquestación con EventBridge y Step Functions

**Estado:** Aceptado — 2026-11-11

## Contexto

El pipeline (2 jobs y 2 crawlers) se ejecutaba a mano. Se quiere que se
dispare solo cuando llega el CSV del TMS a `bronze/`. La ADR 0001 dejaba la
orquestación fuera de alcance.

Opciones evaluadas:

1. **EventBridge → Glue Workflow:** encadena jobs y crawlers de forma nativa,
   pero es específico de Glue, maneja errores de forma limitada y su
   visualización es menos didáctica.
2. **EventBridge → Step Functions:** orquestador general de AWS, con grafo de
   ejecución por paso, `Retry`/`Catch` explícitos y una habilidad que el
   alumno reutiliza en otros servicios.

Según la documentación de Step Functions, Glue solo tiene integración
optimizada para `StartJobRun` (con `.sync`). Los crawlers se invocan con la
integración AWS SDK y no tienen espera nativa.

## Decisión

* Opción 2.
* `s3`: el bucket envía sus eventos a EventBridge (`aws_s3_bucket_notification`
  con `eventbridge = true`).
* `eventbridge`: regla `Object Created` con filtro por bucket **y prefijo
  `bronze/envios/`**; el target es la máquina de estados. Un rol propio con
  `states:StartExecution` solo sobre esa máquina. La regla se puede desactivar
  con `enable_event_trigger`.
* `stepfunctions`: máquina **Standard**:
  `BronzeToSilver (.sync) → crawler silver → SilverToGold (.sync) → crawler gold`.
  Cada crawler sigue un ciclo `Start → Wait → GetCrawler → Choice`. Los jobs
  tienen `Retry` ante `Glue.ConcurrentRunsExceededException`; todos los pasos
  tienen `Catch` hacia `PipelineFailed`. `TimeoutSeconds` acota la ejecución.
* El rol de la máquina vive en su módulo, porque allí se conocen los ARN de
  jobs y crawlers (regla de IAM entre módulos), y solo actúa sobre esos ARN.
  Excepción: las acciones de entrega de logs (`logs:*LogDelivery`, etc.)
  exigen `Resource "*"`.
* Logs de ejecución en `/aws/vendedlogs/states/<prefijo>-pipeline` (módulo
  `cloudwatch`), con retención.

## Consecuencias

* Subir el CSV ejecuta todo el pipeline, y el grafo de la ejecución se ve en la
  consola de Step Functions.
* El filtro por prefijo es crítico: sin él, las escrituras de los jobs en
  `silver/` y `gold/` volverían a disparar el pipeline en un ciclo infinito.
* Glue/EventBridge no deduplican eventos. Como los jobs sobrescriben sus
  salidas, reprocesar es idempotente.
* El ciclo de espera de los crawlers suma estados y transiciones; su costo es
  despreciable a esta escala (confirmar precios de Step Functions Standard).
* Se agregan 2 módulos y 2 roles IAM: el lab se alarga unos 10 minutos de
  explicación.
