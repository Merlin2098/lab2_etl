# ADR 0002 — Glue Data Catalog poblado por crawlers

**Estado:** Aceptado — 2026-11-11

## Contexto

El lab pasa a un caso de logística (ver [01-caso-de-negocio.md](../01-caso-de-negocio.md))
con un esquema gold definido para analítica. La modificación en vivo es un
**cambio de esquema** que debe reflejarse en el Glue Data Catalog y requiere
reprocesar el pipeline. La ADR 0001 dejaba el catálogo fuera de alcance.

Opciones evaluadas para las tablas del catálogo:

1. **Tablas declaradas en Terraform**, generadas desde contratos: esquema
   explícito, pero cada cambio exige `terraform apply` y es poco dinámico.
2. **Escritura desde Spark** (`saveAsTable` / `enableUpdateCatalog`): acopla
   los jobs al catálogo.
3. **Crawlers:** descubren el esquema desde el Parquet y actualizan la tabla
   cuando cambia. Es el patrón habitual en AWS y el más dinámico.

## Decisión

* Opción 3. El módulo `glue` crea `aws_glue_catalog_database` y **dos crawlers**:
  * `<prefijo>-silver-crawler`: target `silver/envios/`, `table_prefix = "silver_"`
    → tabla `silver_envios`.
  * `<prefijo>-gold-crawler`: target `gold/desempeno_rutas/`,
    `table_prefix = "gold_"` → tabla `gold_desempeno_rutas`.
* Cada crawler apunta a la carpeta raíz de su tabla (una ruta de inclusión por
  tabla), como recomienda AWS, para que no fusione tablas como particiones.
* `schema_change_policy`: `update_behavior = "UPDATE_IN_DATABASE"`,
  `delete_behavior = "LOG"`.
* Los crawlers usan el mismo rol IAM de los jobs y no tienen schedule: se
  ejecutan después de cada job (a mano en esta ADR; luego los orquesta Step
  Functions, ver [ADR 0003](0003-orquestacion-eventbridge-step-functions.md)).
* Los contratos de `src/contracts/` se mantienen como **especificación y
  validación**: los jobs verifican sus columnas contra el contrato antes de
  escribir, y los tests en `tests/aws/` comparan la tabla creada por el crawler
  con el contrato.
* Bronze no se cataloga. Silver y gold no se particionan.

## Consecuencias

* Un cambio de esquema es: SQL + contrato → reproceso → crawler. El catálogo
  se actualiza solo, sin tocar Terraform.
* El catálogo depende de que el crawler se ejecute después del job; si no, la
  tabla queda con el esquema anterior. Es un punto didáctico.
* Cada corrida de crawler tiene costo propio, con un mínimo facturable por
  corrida (confirmar en la página de precios). Por eso van sin schedule.
* Sin particiones, cada corrida reescribe la tabla completa. `# debt:` con
  volumen real, particionar por `fecha_despacho` y dejar que el crawler
  registre las particiones.
* Consultar el catálogo con SQL (Athena) sigue fuera de alcance.
