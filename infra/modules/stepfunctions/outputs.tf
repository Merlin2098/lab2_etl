output "state_machine_arn" {
  description = "ARN de la máquina de estados del pipeline."
  value       = aws_sfn_state_machine.pipeline.arn
}

output "state_machine_name" {
  description = "Nombre de la máquina de estados del pipeline."
  value       = aws_sfn_state_machine.pipeline.name
}

output "resource_arn" {
  description = "ARN del recurso principal del módulo (máquina de estados)."
  value       = aws_sfn_state_machine.pipeline.arn
}
