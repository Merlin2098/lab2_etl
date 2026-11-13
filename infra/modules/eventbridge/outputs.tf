output "rule_name" {
  description = "Nombre de la regla que dispara el pipeline."
  value       = aws_cloudwatch_event_rule.bronze_upload.name
}

output "resource_arn" {
  description = "ARN del recurso principal del módulo (regla)."
  value       = aws_cloudwatch_event_rule.bronze_upload.arn
}
