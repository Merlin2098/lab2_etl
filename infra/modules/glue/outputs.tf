output "job_names" {
  description = "Nombres de los Glue jobs, por clave (bronze-to-silver, silver-to-gold)."
  value       = { for k, job in aws_glue_job.this : k => job.name }
}

output "job_arns" {
  description = "ARN de los Glue jobs, por clave."
  value       = { for k, job in aws_glue_job.this : k => job.arn }
}

output "crawler_arns" {
  description = "ARN de los crawlers, por capa."
  value       = { for k, crawler in aws_glue_crawler.layer : k => crawler.arn }
}

output "crawler_names" {
  description = "Nombres de los crawlers, por capa (silver, gold)."
  value       = { for k, crawler in aws_glue_crawler.layer : k => crawler.name }
}

output "database_name" {
  description = "Base de datos del Data Catalog."
  value       = aws_glue_catalog_database.lake.name
}

output "resource_arn" {
  description = "ARN del recurso principal del módulo (base del Data Catalog)."
  value       = aws_glue_catalog_database.lake.arn
}
