# Glue 5.x escribe los logs de los jobs en <prefijo>/error y <prefijo>/output
# cuando el job recibe --custom-logGroup-prefix. Se crean antes del primer run
# para que tengan retención (si no, Glue los crea sin ella).

locals {
  glue_log_prefix = "/aws-glue/${var.name_prefix}"
}

resource "aws_cloudwatch_log_group" "glue_error" {
  name              = "${local.glue_log_prefix}/error"
  retention_in_days = var.retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "glue_output" {
  name              = "${local.glue_log_prefix}/output"
  retention_in_days = var.retention_days
  tags              = var.tags
}

# Logs de ejecución de Step Functions. El prefijo /aws/vendedlogs/ es el que
# AWS recomienda para logs de servicios vendidos (evita el límite de tamaño de
# la resource policy de CloudWatch Logs).
resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/aws/vendedlogs/states/${var.name_prefix}-pipeline"
  retention_in_days = var.retention_days
  tags              = var.tags
}

# Los crawlers NO tienen log group aquí: Glue los hace escribir en el log group
# compartido de la cuenta /aws-glue/crawlers (un log stream por crawler). No se
# gestiona con Terraform; ver docs/03-implementacion.md § 2.4.
