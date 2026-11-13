variable "name_prefix" {
  description = "Prefijo de nombres (<proyecto>-<entorno>)."
  type        = string
}

variable "job_names" {
  description = "Nombres de los Glue jobs por clave (bronze-to-silver, silver-to-gold)."
  type        = map(string)
}

variable "job_arns" {
  description = "ARN de los Glue jobs por clave."
  type        = map(string)
}

variable "crawler_names" {
  description = "Nombres de los crawlers por capa (silver, gold)."
  type        = map(string)
}

variable "crawler_arns" {
  description = "ARN de los crawlers por capa."
  type        = map(string)
}

variable "log_group_arn" {
  description = "ARN del log group de Step Functions."
  type        = string
}

variable "crawler_poll_seconds" {
  description = "Segundos entre consultas del estado de un crawler."
  type        = number
}

variable "pipeline_timeout_seconds" {
  description = "Timeout total de una ejecución del pipeline."
  type        = number
}

variable "tags" {
  description = "Etiquetas comunes aplicadas a todos los recursos."
  type        = map(string)
}
