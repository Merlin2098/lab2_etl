# 5. Cambio en vivo: evolución de esquema con un agente de IA

> Ruta de lectura: [1. Caso de negocio](01-caso-de-negocio.md) →
> [2. Arquitectura](02-arquitectura.md) →
> [3. Implementación técnica](03-implementacion.md) →
> [4. Validación con Athena](04-validacion-athena.md) → **5. Cambio en vivo**

Al final del lab se hace, en vivo y en ≤ 15 minutos, un **cambio de esquema**
pidiéndoselo a un agente de IA. El objetivo es practicar cómo pedir un cambio
**acotado**, revisar lo que propone el agente y verificar el resultado en el
pipeline.

## 5.1 La historia

Operaciones necesita vigilar la **cadena de frío**. El OTD agregado por ruta
esconde que la carga `REFRIGERADA` se entrega tarde más seguido. Piden ver los
indicadores de gold **separados por tipo de carga**.

Por qué este cambio:

* Es un **cambio de esquema real**: columna nueva y **cambio de granularidad**
  (fecha × ruta → fecha × ruta × tipo de carga).
* El dato ya existe en silver: no hay que tocar el generador ni reprocesar
  bronze.
* No toca Terraform ni IAM: el crawler actualiza el catálogo solo.

## 5.2 Qué debería cambiar (2 archivos)

| Archivo | Cambio |
|---|---|
| `src/transformations/silver_to_gold.sql` | Agregar `tipo_carga` al `select` (después de `destino`) y al `group by` |
| `src/contracts/gold_desempeno_rutas.json` | Agregar `tipo_carga string` después de `destino`; actualizar `primary_key` y `description` |

SQL y contrato van **siempre juntos**: el job compara su salida con el contrato
y falla si no coinciden (ver [3. Implementación § 4](03-implementacion.md#4-scripts-de-glue-srcjobs)).

## 5.3 El prompt

> Operaciones quiere los indicadores de `gold_desempeno_rutas` separados por
> `tipo_carga`. Agrega `tipo_carga` como dimensión (justo después de `destino`)
> en `src/transformations/silver_to_gold.sql` y en el contrato
> `src/contracts/gold_desempeno_rutas.json`, incluida la clave primaria.
> Cambio mínimo: no toques Terraform, IAM, silver ni otras columnas. Primero
> muéstrame qué archivos vas a modificar y luego el diff.

Elementos de un buen prompt de cambio: **dónde** (archivos), **qué** (columna
y posición), **restricciones** (qué no tocar) y **cómo revisar** (plan y diff
antes de aplicar).

## 5.4 Guion y tiempos

Tiempos medidos de una ejecución completa del pipeline (1030 filas, Glue 5.1,
2×G.1X):

| Paso del pipeline | 1.ª ejecución (en frío) | 2.ª ejecución |
|---|---|---|
| BronzeToSilver | 5:51 | 2:17 |
| Crawler silver | 2:35 | ~0:31 |
| SilverToGold | 3:53 | 2:04 |
| Crawler gold | ~0:48 | ~3:07 |
| **Total** | **12:55** | **7:51** |

El pipeline completo **no entra** con holgura en 15 minutos. Como el cambio
solo afecta gold, en vivo se reprocesa **solo `silver-to-gold` + crawler
gold** (~3–5 min):

| Min | Paso |
|---|---|
| 0–4 | Prompt, plan del agente y **revisión del diff en voz alta** (la IA propone, la persona aprueba) |
| 4–5 | `uv run python scripts/testing/run_pytest.py tests/test_contracts.py`: el chequeo local de contrato vs. SQL pasa |
| 5–6 | `terraform -chdir=infra apply`: el `plan` muestra **solo** 2 objetos S3 re-subidos (el SQL y el contrato) |
| 6–10 | `aws glue start-job-run --job-name lab2-etl-dev-silver-to-gold`. Mientras corre, mostrar en el grafo de una ejecución anterior de Step Functions dónde encaja este paso |
| 10–11 | `aws glue start-crawler --name lab2-etl-dev-gold-crawler` |
| 11–15 | En la consola: tabla `gold_desempeno_rutas` con `tipo_carga` y su **historial de versiones**; en Athena, el OTD por tipo de carga ([4. Validación § 5](04-validacion-athena.md#5-después-del-cambio-en-vivo)): `REFRIGERADA` claramente menor |

La orquestación event-driven completa (subir el CSV y seguir el grafo) se
muestra **antes**, en la parte guiada del lab, donde hay tiempo para los
~8–13 minutos.

## 5.5 Para discutir después

* ¿El agente tocó solo los 2 archivos esperados? ¿Qué mostró el `plan`?
* ¿Qué pasa si se cambia el SQL pero no el contrato? El job falla antes de
  escribir. ¿Y si no se ejecuta el crawler? El Parquet trae la columna, pero el
  catálogo no la expone.
* Cambiar la granularidad es un **breaking change** para los consumidores: una
  consulta que suma por ruta sigue funcionando, pero un dashboard que asumía
  "una fila por ruta y día" ahora duplica valores.

## 5.6 Tarea para casa (≈ 25 min)

El TMS empieza a exportar `costo_operativo_pen` por envío y Finanzas quiere el
**margen por ruta** (`margen_pen = ingreso_total_pen − costo_total_pen`). Toca
el generador, ambos SQL, ambos contratos, y requiere el pipeline completo
(ambos jobs y ambos crawlers).

## 5.7 Notas para el instructor

* **Variante más corta (≈ 10 min):** agregar una métrica en lugar de una
  dimensión, por ejemplo `envios_tarde bigint` (entregados − a tiempo). Mismos
  2 archivos, sin cambio de granularidad.
* **Si Glue tarda en arrancar:** mostrar mientras tanto la definición de la
  máquina de estados o el log del job en CloudWatch.
* **Si una ejecución no arranca al subir el CSV:** revisar que la regla de
  EventBridge esté `ENABLED` y lanzar a mano con
  `uv run python scripts/check_pipeline.py --start`.
* **Plan B:** tener grabada una corrida exitosa y la salida "antes" de gold ya
  generada, para comparar antes y después.
* Guardar el prompt en `docs/prompt/` (está en `.gitignore`).
* Después del cambio, `uv run python scripts/check_pipeline.py --start`
  reprocesa todo y confirma que el catálogo coincide con el contrato nuevo (si
  sobra tiempo).
