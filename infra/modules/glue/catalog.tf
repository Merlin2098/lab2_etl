# Data Catalog: Terraform crea la base y los crawlers; las tablas las crean y
# actualizan los crawlers (no forman parte del estado de Terraform).

resource "aws_glue_catalog_database" "lake" {
  name        = replace(var.name_prefix, "-", "_")
  description = "Lab 2: tablas silver y gold del lake, registradas por crawlers."
  tags        = var.tags
}

locals {
  # Una ruta por tabla (recomendación de AWS) para que el crawler no fusione
  # tablas como particiones. Nombre de tabla = table_prefix + carpeta.
  crawlers = {
    silver = "silver/envios/"        # -> silver_envios
    gold   = "gold/desempeno_rutas/" # -> gold_desempeno_rutas
  }
}

resource "aws_glue_crawler" "layer" {
  for_each = local.crawlers

  name          = "${var.name_prefix}-${each.key}-crawler"
  description   = "Lab 2: registra la capa ${each.key} en el Data Catalog."
  role          = var.role_arn
  database_name = aws_glue_catalog_database.lake.name
  table_prefix  = "${each.key}_"

  s3_target {
    path       = "s3://${var.bucket_name}/${each.value}"
    exclusions = ["**_SUCCESS"] # marcador de Spark; no es dato
  }

  # Al cambiar el esquema del Parquet, el crawler actualiza la tabla.
  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  # Sin schedule: se ejecuta a mano después de cada job.
  tags = var.tags
}
