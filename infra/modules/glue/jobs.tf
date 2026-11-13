# Dos Glue jobs Spark batch. Comparten configuración y solo difieren en el
# script, el SQL y el contrato contra el que validan su salida.

locals {
  jobs = {
    "bronze-to-silver" = { script = "bronze_to_silver", contract = "silver_envios" }
    "silver-to-gold"   = { script = "silver_to_gold", contract = "gold_desempeno_rutas" }
  }
  code_prefix = "s3://${var.bucket_name}/scripts"
}

resource "aws_glue_job" "this" {
  for_each = local.jobs

  name              = "${var.name_prefix}-${each.key}"
  description       = "Lab 2: ${each.value.script} (contrato ${each.value.contract})"
  role_arn          = var.role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = var.timeout_minutes
  max_retries       = 0
  execution_class   = "STANDARD"

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "${local.code_prefix}/${each.value.script}.py"
  }

  default_arguments = {
    # Parámetros propios del lab (se leen con getResolvedOptions).
    "--bucket"        = var.bucket_name
    "--sql_file"      = "${each.value.script}.sql"
    "--contract_file" = "${each.value.contract}.json"

    # --extra-files copia el SQL y el contrato al directorio de trabajo del driver.
    "--extra-files" = join(",", [
      "${local.code_prefix}/sql/${each.value.script}.sql",
      "${local.code_prefix}/contracts/${each.value.contract}.json",
    ])

    # Evita que Glue cree un bucket temporal propio (podría ser público).
    "--TempDir"                = "s3://${var.bucket_name}/tmp/"
    "--job-bookmark-option"    = "job-bookmark-disable"
    "--custom-logGroup-prefix" = var.log_group_prefix
  }

  tags = var.tags
}
