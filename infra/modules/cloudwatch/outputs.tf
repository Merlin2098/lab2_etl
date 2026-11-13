output "log_group_prefix" {
  description = "Prefijo para --custom-logGroup-prefix de los Glue jobs."
  # Derivado del recurso para que los jobs dependan de que el log group exista.
  value = trimsuffix(aws_cloudwatch_log_group.glue_error.name, "/error")
}

output "log_group_name" {
  description = "Log group de errores de los Glue jobs."
  value       = aws_cloudwatch_log_group.glue_error.name
}

output "log_group_arn" {
  description = "ARN del log group de errores de los Glue jobs."
  value       = aws_cloudwatch_log_group.glue_error.arn
}

output "output_log_group_name" {
  description = "Log group de stdout de los Glue jobs."
  value       = aws_cloudwatch_log_group.glue_output.name
}

output "pipeline_log_group_arn" {
  description = "ARN del log group de Step Functions."
  value       = aws_cloudwatch_log_group.pipeline.arn
}

output "resource_arn" {
  description = "ARN del recurso principal del módulo (log group de errores)."
  value       = aws_cloudwatch_log_group.glue_error.arn
}
