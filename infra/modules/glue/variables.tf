variable "name_prefix" {
  description = "Prefijo de nombres (<proyecto>-<entorno>)."
  type        = string
}

variable "bucket_name" {
  description = "Bucket del lake (datos, scripts y TempDir)."
  type        = string
}

variable "role_arn" {
  description = "ARN del rol IAM que usan jobs y crawlers."
  type        = string
}

variable "log_group_prefix" {
  description = "Prefijo de log groups para --custom-logGroup-prefix."
  type        = string
}

variable "glue_version" {
  description = "Versión de AWS Glue."
  type        = string
}

variable "worker_type" {
  description = "Tipo de worker de Glue."
  type        = string
}

variable "number_of_workers" {
  description = "Número de workers por job."
  type        = number
}

variable "timeout_minutes" {
  description = "Timeout de cada job en minutos."
  type        = number
}

variable "tags" {
  description = "Etiquetas comunes aplicadas a todos los recursos."
  type        = map(string)
}
