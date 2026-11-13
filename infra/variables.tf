variable "project_name" {
  description = "Nombre del proyecto; se usa en nombres y en la etiqueta Project."
  type        = string
  default     = "lab2-etl"
}

variable "environment" {
  description = "Entorno de despliegue."
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Etiqueta Owner de todos los recursos."
  type        = string
  default     = "data-engineering"
}

variable "cost_center" {
  description = "Etiqueta CostCenter de todos los recursos."
  type        = string
  default     = "bootcamp-aws-dea"
}

variable "aws_region" {
  description = "Región de AWS."
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Etiquetas adicionales para todos los recursos."
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  description = "Retención de CloudWatch Logs en días (7 para labs)."
  type        = number
  default     = 7
}

variable "enable_event_trigger" {
  description = "Disparar el pipeline al subir un CSV a bronze/envios/. false = solo ejecución manual."
  type        = bool
  default     = true
}

variable "crawler_poll_seconds" {
  description = "Segundos entre consultas del estado de un crawler en Step Functions."
  type        = number
  default     = 20
}

variable "pipeline_timeout_seconds" {
  description = "Timeout total de una ejecución del pipeline (corta ciclos de espera colgados)."
  type        = number
  default     = 1800
}

variable "glue_version" {
  description = "Versión de AWS Glue (5.1 = Spark 3.5.6, Python 3.11)."
  type        = string
  default     = "5.1"
}

variable "glue_worker_type" {
  description = "Tipo de worker de Glue."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Workers por job (mínimo 2 para G.1X)."
  type        = number
  default     = 2

  validation {
    condition     = var.glue_number_of_workers >= 2 && var.glue_number_of_workers <= 4
    error_message = "Para el lab usar entre 2 y 4 workers; subirlo requiere aprobación."
  }
}

variable "glue_timeout_minutes" {
  description = "Timeout de cada job en minutos (Glue 5.x usa 480 por defecto)."
  type        = number
  default     = 10

  validation {
    condition     = var.glue_timeout_minutes > 0 && var.glue_timeout_minutes <= 30
    error_message = "Para el lab usar un timeout entre 1 y 30 minutos."
  }
}
