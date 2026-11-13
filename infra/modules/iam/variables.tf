variable "name_prefix" {
  description = "Prefijo de nombres (<proyecto>-<entorno>)."
  type        = string
}

variable "bucket_arn" {
  description = "ARN del bucket del lake al que accede el rol."
  type        = string
}

variable "tags" {
  description = "Etiquetas comunes aplicadas a todos los recursos."
  type        = map(string)
}
