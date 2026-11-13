variable "name_prefix" {
  description = "Prefijo de nombres (<proyecto>-<entorno>)."
  type        = string
}

variable "retention_days" {
  description = "Retención de los log groups en días."
  type        = number
}

variable "tags" {
  description = "Etiquetas comunes aplicadas a todos los recursos."
  type        = map(string)
}
