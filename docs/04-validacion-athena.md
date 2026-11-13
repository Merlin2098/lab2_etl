# 4. Validación de la capa gold con Athena

> Ruta de lectura: [1. Caso de negocio](01-caso-de-negocio.md) →
> [2. Arquitectura](02-arquitectura.md) →
> [3. Implementación técnica](03-implementacion.md) →
> **4. Validación con Athena** → [5. Cambio en vivo](05-cambio-en-vivo.md)

Cuatro consultas para revisar en Amazon Athena los KPIs de
`gold_desempeno_rutas`, una por cada pregunta del
[caso de negocio](01-caso-de-negocio.md#2-el-problema). Sirven para comprobar que
el pipeline produjo datos coherentes y para mostrar en clase cómo un analista
consume la capa gold desde el Data Catalog.

> Athena no se despliega con Terraform en este lab: se usa directamente desde
> la consola sobre las tablas que registraron los crawlers.

## 1. Preparación (una sola vez)

1. Ejecutar el pipeline al menos una vez (ver [README § 3](../README.md#3-probar-la-solución-de-punta-a-punta-e2e)),
   para que existan las tablas en el catálogo.
2. En la consola: **Athena → Query editor → Settings → Manage** y definir la
   ubicación de resultados:

   ```
   s3://<proyecto>-<entorno>-<cuenta>-lake/athena-results/
   ```

   Por ejemplo, `s3://lab2-etl-dev-<cuenta>-lake/athena-results/`. Queda dentro
   del bucket del lab, así que `terraform destroy` también la elimina.
3. En el editor, elegir **Data source** `AwsDataCatalog` y **Database**
   `lab2_etl_dev`.

Costo: Athena cobra por datos escaneados; con estos Parquet de pocos KB, cada
consulta cuesta una fracción de centavo (confirmar en la página de precios).

## 2. Regla para agregar KPIs

Cada fila de gold es **un día × una ruta** (`fecha_despacho`, `origen`,
`destino`). Al agregar varios días, los porcentajes y promedios se **recalculan
desde las sumas**: promediar `otd_pct` día a día daría un resultado incorrecto,
porque cada día tiene una cantidad distinta de envíos.

| KPI | Cálculo correcto al agregar |
|---|---|
| OTD | `SUM(envios_a_tiempo) / SUM(envios_entregados)` |
| Días de tránsito | `SUM(dias_transito_prom * envios_entregados) / SUM(envios_entregados)` |
| Ingreso por kg | `SUM(ingreso_total_pen) / SUM(peso_total_kg)` |

## 3. Consultas

### 3.1 Puntualidad: OTD por ruta frente a la meta del 95 %

Pregunta de negocio: *¿Qué rutas cumplen el compromiso de entrega?*

```sql
SELECT
    origen,
    destino,
    SUM(envios_entregados)                                         AS entregados,
    SUM(envios_a_tiempo)                                           AS a_tiempo,
    ROUND(100.0 * SUM(envios_a_tiempo)
          / NULLIF(SUM(envios_entregados), 0), 2)                  AS otd_pct,
    CASE WHEN 100.0 * SUM(envios_a_tiempo)
              / NULLIF(SUM(envios_entregados), 0) >= 95
         THEN 'CUMPLE' ELSE 'NO CUMPLE' END                        AS meta_95
FROM lab2_etl_dev.gold_desempeno_rutas
GROUP BY origen, destino
ORDER BY otd_pct ASC;
```

**Qué validar**

* 10 filas: 5 destinos, en ambos sentidos (Lima ↔ ciudad).
* `otd_pct` entre 0 y 100.
* Los datos de prueba tienen alrededor de 10 % de entregas tardías, así que lo
  esperado es que varias rutas den `NO CUMPLE`.

### 3.2 Tiempo de tránsito promedio por ruta

Pregunta de negocio: *¿Cuántos días tarda en promedio cada ruta?*

```sql
SELECT
    origen,
    destino,
    SUM(envios_entregados)                                         AS entregados,
    ROUND(SUM(dias_transito_prom * envios_entregados)
          / NULLIF(SUM(envios_entregados), 0), 2)                  AS dias_transito_prom,
    MIN(dias_transito_prom)                                        AS mejor_dia,
    MAX(dias_transito_prom)                                        AS peor_dia
FROM lab2_etl_dev.gold_desempeno_rutas
WHERE envios_entregados > 0
GROUP BY origen, destino
ORDER BY dias_transito_prom DESC;
```

**Qué validar**

* El promedio va ponderado por la cantidad de entregados.
* Debe quedar algo por encima del tránsito comprometido de cada ruta: Trujillo
  1 día; Arequipa y Chiclayo 2; Piura y Cusco 3. La diferencia son las entregas
  tardías.

### 3.3 Volumen diario despachado

Pregunta de negocio: *¿Cuánto volumen movemos por día?*

```sql
SELECT
    fecha_despacho,
    SUM(envios_total)                                              AS envios,
    SUM(envios_entregados)                                         AS entregados,
    SUM(envios_total) - SUM(envios_entregados)                     AS en_transito,
    SUM(peso_total_kg)                                             AS peso_total_kg
FROM lab2_etl_dev.gold_desempeno_rutas
GROUP BY fecha_despacho
ORDER BY fecha_despacho;
```

**Qué validar**

* Una fila por día de despacho, cubriendo los 14 días previos a cada lote
  cargado.
* `en_transito` crece en los últimos días: esos envíos aún no llegaban cuando
  se generó el archivo. Es lo esperado, no un error.

### 3.4 Ingreso por ruta y por kg transportado

Pregunta de negocio: *¿Cuánto ingreso genera cada ruta y cuánto por kg?*

```sql
SELECT
    origen,
    destino,
    SUM(ingreso_total_pen)                                         AS ingreso_pen,
    SUM(peso_total_kg)                                             AS peso_kg,
    ROUND(SUM(ingreso_total_pen)
          / NULLIF(SUM(peso_total_kg), 0), 4)                      AS ingreso_por_kg_pen,
    ROUND(100.0 * SUM(ingreso_total_pen)
          / SUM(SUM(ingreso_total_pen)) OVER (), 2)                AS participacion_pct
FROM lab2_etl_dev.gold_desempeno_rutas
GROUP BY origen, destino
ORDER BY ingreso_pen DESC;
```

**Qué validar**

* `participacion_pct` suma 100.
* `ingreso_por_kg_pen` sigue la tarifa base de cada ruta (Cusco la más cara,
  Trujillo la más barata) más el recargo por tipo de carga (refrigerada
  ×1.35, peligrosa ×1.6).

## 4. Cómo leer los resultados con varios lotes cargados

Cada ejecución del pipeline reprocesa **todo** bronze, así que gold acumula
todos los lotes cargados. Ejemplo: con los lotes del 12 y del 13 de noviembre,
gold tiene 150 filas.

Como los envíos de cada lote se despacharon en los 14 días anteriores, los
rangos de fechas se solapan y en esas fechas hay envíos de ambos lotes. No son
duplicados: los IDs son distintos (`GR-20261112-…`, `GR-20261113-…`).

## 5. Después del cambio en vivo

Tras agregar `tipo_carga` a gold (ver
[05-cambio-en-vivo.md](05-cambio-en-vivo.md)),
la granularidad pasa a ser día × ruta × tipo de carga. Las consultas de arriba
siguen funcionando porque agregan con sumas. Para mostrar el hallazgo del caso
(la cadena de frío), agrupar por `tipo_carga`:

```sql
SELECT
    tipo_carga,
    SUM(envios_entregados)                                         AS entregados,
    ROUND(100.0 * SUM(envios_a_tiempo)
          / NULLIF(SUM(envios_entregados), 0), 2)                  AS otd_pct
FROM lab2_etl_dev.gold_desempeno_rutas
GROUP BY tipo_carga
ORDER BY otd_pct;
```

Lo esperado es que `REFRIGERADA` tenga un OTD claramente menor que `GENERAL`.

> Una consulta que **no** agregue (por ejemplo, un dashboard que asuma una fila
> por día y ruta) duplicaría valores tras el cambio: es el *breaking change*
> que se discute en clase.
