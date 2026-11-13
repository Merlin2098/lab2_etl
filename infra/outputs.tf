output "lake_bucket_name" {
  description = "Bucket del lake (usar como LAB_BUCKET en el generador)."
  value       = module.s3.bucket_name
}

output "lake_bucket_arn" {
  description = "ARN del bucket del lake."
  value       = module.s3.resource_arn
}

output "glue_role_arn" {
  description = "Rol IAM de jobs y crawlers."
  value       = module.iam.role_arn
}

output "glue_job_names" {
  description = "Glue jobs (bronze-to-silver, silver-to-gold)."
  value       = module.glue.job_names
}

output "glue_crawler_names" {
  description = "Crawlers por capa (silver, gold)."
  value       = module.glue.crawler_names
}

output "glue_database_name" {
  description = "Base de datos del Data Catalog."
  value       = module.glue.database_name
}

output "pipeline_state_machine_arn" {
  description = "Máquina de estados del pipeline (para start-execution manual)."
  value       = module.stepfunctions.state_machine_arn
}

output "pipeline_trigger_rule" {
  description = "Regla de EventBridge que dispara el pipeline."
  value       = module.eventbridge.rule_name
}

output "log_group_name" {
  description = "Log group de errores de los Glue jobs."
  value       = module.cloudwatch.log_group_name
}

output "log_group_arn" {
  description = "ARN del log group de errores de los Glue jobs."
  value       = module.cloudwatch.log_group_arn
}

output "code_object_keys" {
  description = "Código subido a scripts/ para los jobs."
  value       = module.s3.code_object_keys
}
