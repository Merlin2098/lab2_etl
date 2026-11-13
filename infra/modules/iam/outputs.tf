output "role_arn" {
  description = "ARN del rol de Glue (jobs y crawlers)."
  # Depende de las policies para que nadie use el rol antes de tener permisos.
  value = aws_iam_role.glue.arn

  depends_on = [
    aws_iam_role_policy_attachment.glue_service_role,
    aws_iam_role_policy.lake_access,
  ]
}

output "role_name" {
  description = "Nombre del rol de Glue."
  value       = aws_iam_role.glue.name
}

output "resource_arn" {
  description = "ARN del recurso principal del módulo (rol)."
  value       = aws_iam_role.glue.arn
}
