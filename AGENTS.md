# AGENTS.md

Contrato de trabajo para agentes de IA (Claude, Codex, etc.) en este
repositorio.

## Qué es este proyecto

**Lab 2 — ETL serverless en AWS con arquitectura medallion.** Es un laboratorio
práctico y **corto** para el bootcamp AWS Data Engineer, sobre el caso de un
operador de carga ficticio. El índice completo está en el
[README](README.md#índice); léelos antes de cualquier tarea:

* [docs/01-caso-de-negocio.md](docs/01-caso-de-negocio.md): dominio, esquemas
  silver y gold, KPIs
* [docs/02-arquitectura.md](docs/02-arquitectura.md): diseño del lab y decisiones
* [docs/03-implementacion.md](docs/03-implementacion.md): detalle técnico y
  hallazgos del despliegue
* [docs/04-validacion-athena.md](docs/04-validacion-athena.md): consultas de
  validación de gold
* [docs/05-cambio-en-vivo.md](docs/05-cambio-en-vivo.md): guion del cambio de
  esquema con IA

La documentación está numerada en orden de lectura. Un documento nuevo para
alumnos lleva el siguiente número (`06-...`), su línea de "Ruta de lectura" y
una entrada en el índice del README.

Alcance cerrado del lab:

* **1 bucket S3** con tres prefijos: `bronze/`, `silver/`, `gold/`
* **2 Glue jobs** (procesamiento **batch**):
  * `bronze_to_silver`: lee CSV crudo, tipa, limpia, deduplica → Parquet
  * `silver_to_gold`: agrega KPIs por ruta → Parquet
* **Glue Data Catalog** con **2 crawlers** (silver y gold)
* **Orquestación** event-driven: S3 → **EventBridge** (regla filtrada por
  `bronze/envios/`) → **Step Functions** (job → crawler → job → crawler). La
  regla se puede desactivar para ejecutar a mano
* **1 script Python local** que simula el export del TMS (CSV) y lo sube a
  `bronze/`
* Infraestructura en **Terraform** (`infra/`), modularizada con **un módulo por
  servicio** en `infra/modules/<servicio>/` (`s3`, `iam`, `cloudwatch`, `glue`,
  `stepfunctions`, `eventbridge`). La raíz (`infra/main.tf`) solo define locals
  y llama a módulos; no declara recursos.

Fuera de alcance salvo que el usuario lo pida explícitamente: Lambda, Glue
Workflows, schedules de crawlers, Athena, Lake Formation, streaming, CI/CD,
AWS Budgets, módulos Terraform adicionales, frameworks de calidad de datos.

### Orquestación

* La regla de EventBridge **siempre** filtra por el prefijo `bronze/envios/`.
  Nunca ampliarla a todo el bucket: los jobs escriben `silver/` y `gold/` en el
  mismo bucket y se generaría un ciclo infinito de ejecuciones.
* Un paso nuevo del pipeline (job o crawler) se agrega en la definición de
  `modules/stepfunctions` y su ARN en la policy del rol de la máquina.

### Cambios de esquema

Un cambio de esquema se hace siempre como **SQL + contrato**
(`src/contracts/<tabla>.json`) en el mismo cambio. Después se reprocesa el
pipeline (subiendo el CSV o con `start-execution`), que incluye los crawlers.
Las tablas del catálogo no se declaran en Terraform: las gestionan los
crawlers.

---

## Comportamiento esperado

* Es material didáctico: cada archivo debe poder explicarse en clase en pocos
  minutos. Prioriza legibilidad sobre generalidad.
* **Cambio mínimo**: cuando se pida una modificación, implementa el cambio más
  pequeño que la resuelva. No refactorices ni "mejores" código no relacionado.
* Busca lo que ya existe antes de crear archivos nuevos; extiende en lugar de
  duplicar.
* SQL de transformación en `src/transformations/*.sql`, separado del Python.
* Rutas, nombres de bucket y parámetros en configuración (`src/config/`,
  variables de Terraform, argumentos de Glue), nunca hardcodeados.
* Para comportamiento de servicios AWS o sintaxis de Terraform, consulta los
  MCP de AWS Documentation / Terraform en vivo en vez de asumir.

El agente no debe:

* crear frameworks, capas de abstracción ni orquestadores propios
* añadir servicios AWS fuera del alcance anterior sin aprobación
* añadir dependencias si la stdlib o el runtime de Glue ya lo resuelven

---

## Comandos

* Entorno: `uv sync` (o `scripts/python/setup_env.sh` / `.ps1`)
* Tests: `python scripts/testing/run_pytest.py`
* Lint/format: `python scripts/testing/run_ruff_check.py`,
  `python scripts/testing/run_ruff_format.py`
* Terraform: siempre desde `infra/` (`terraform -chdir=infra plan`)
* Generar datos: `uv run python scripts/generate_envios_csv.py [--upload]`
  (`--upload` sube a bronze/ y **dispara el pipeline en AWS**: pedir
  aprobación antes de ejecutarlo)
* Probar el pipeline: `uv run python scripts/check_pipeline.py [--upload|--start]`
  (`--upload`/`--start` ejecutan el pipeline en AWS: pedir aprobación)
* Diagrama: `docs/architecture/architecture.dot` (Graphviz) + `arch2.png`; actualizar ambos al agregar o
  quitar recursos de Terraform

Terminal por defecto: Git Bash. Nada de automatización oculta.

---

## Límites de aprobación

### Nunca sin aprobación

* `terraform apply` / `terraform destroy` / `terraform import`
* modificar estado de infraestructura
* borrar o sobrescribir datos en S3 o artefactos generados por el usuario

### Preguntar antes

* cambios de IAM
* añadir servicios AWS de pago o subir capacidad de Glue (workers, tipo,
  timeout) por encima de lo documentado
* cambios en contratos de datos (`src/contracts/`)
* borrar log groups o reducir su retención

---

## Guardrails AWS/Terraform (obligatorios)

* Bucket privado: block public access, cifrado SSE-S3, `force_destroy = true`
  (es un lab desechable) y **versionado deshabilitado**, declarado
  explícitamente con `aws_s3_bucket_versioning` en `status = "Disabled"`; no
  exponerlo como variable ni cambiarlo sin aprobación
* IAM de mínimo privilegio: el rol de Glue solo accede al bucket del lab y a
  su log group; sin `Resource = "*"` salvo lo que exija la policy gestionada
  de Glue
* Declarar `aws_cloudwatch_log_group` explícito con `retention_in_days`.
  Única excepción: `/aws-glue/crawlers`, que Glue impone a todos los crawlers y
  comparte toda la cuenta. No se declara ni se importa al estado (`destroy`
  borraría logs de otros proyectos). Ver docs/03-implementacion.md § 2.4
* Etiquetas comunes (incluye `CostCenter`) en todos los recursos
* Glue con capacidad mínima (2 workers G.1X) y timeout corto
* Cada módulo expone `resource_arn`; el módulo `cloudwatch` expone además
  `log_group_name` y `log_group_arn`
* Un recurso nuevo va en el módulo de su servicio; si el servicio no tiene
  módulo, se crea `infra/modules/<servicio>/` (`main.tf`, `variables.tf`,
  `outputs.tf`)
* IAM entre módulos: la policy va en el módulo donde se conoce el ARN destino,
  sin crear dependencias circulares
* No borrar ni sobrescribir `terraform.tfstate`
* Al desplegar infraestructura, añadir validaciones boto3 en `tests/aws/`

## Seguridad

* Secretos nunca en código: `.env.credentials` (gitignored) o variables de
  entorno
* Nunca enviar `.env*`, llaves (`.pem`, `.key`, …) ni contenido de `~/.aws`,
  `~/.ssh` a servicios externos

## Gobernanza

* **ADR antes de cambiar la arquitectura** (nuevo servicio, nueva capa,
  cambio de contrato): registrar en `docs/adr/` con formato título, estado,
  contexto, decisión, consecuencias.
* Para cambios pequeños no hace falta spec; basta con que el cambio sea
  coherente con [docs/02-arquitectura.md](docs/02-arquitectura.md).
* Atajos deliberados llevan un comentario `# debt:` con su límite.

---

Simple. Explícito. Reproducible.
