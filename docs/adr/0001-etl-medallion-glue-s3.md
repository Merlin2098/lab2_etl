# ADR 0001 — ETL medallion con 1 bucket S3 y 2 Glue jobs batch

**Estado:** Aceptado — 2026-11-10

## Contexto

El repositorio parte de un template genérico (bucket de artefactos, job de
ejemplo `orders_curated`, instaladores). El Lab 2 necesita un ETL serverless
que se explique y ejecute en una sesión corta, con costo mínimo y fácil de
destruir.

## Decisión

* Un único bucket S3 con prefijos `bronze/`, `silver/`, `gold/` (y `scripts/`
  para el código de Glue).
* Dos Glue jobs Spark (Glue 5.1 — versión por defecto de AWS, Spark 3.5.6,
  Python 3.11 —, 2 workers G.1X, timeout 10 min):
  `bronze_to_silver` y `silver_to_gold`, ejecutados manualmente en batch.
* La lógica de transformación vive en archivos SQL ejecutados con `spark.sql`.
* Datos de entrada: CSV generados localmente con un script Python (stdlib).
* Se retira el job de ejemplo del template y sus artefactos asociados.

## Consecuencias

* ~~Sin orquestador~~: la orquestación con EventBridge + Step Functions se
  incorpora en la [ADR 0003](0003-orquestacion-eventbridge-step-functions.md).
* ~~Sin Data Catalog/Athena~~: el Data Catalog se incorpora en la
  [ADR 0002](0002-data-catalog-con-crawlers.md); Athena sigue fuera de alcance.
* El dominio cambia de ventas a envíos de un operador de carga
  ([caso de negocio](../01-caso-de-negocio.md)).
* Un solo bucket simplifica IAM, pero en producción se separarían buckets por
  capa con políticas distintas.
