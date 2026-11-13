variable "name_prefix" {
  description = "Prefijo de nombres (<proyecto>-<entorno>)."
  type        = string
}

variable "bucket_name" {
  description = "Bucket del lake que emite los eventos Object Created."
  type        = string
}

variable "trigger_prefix" {
  description = "Prefijo de clave que dispara el pipeline."
  type        = string
}

variable "state_machine_arn" {
  description = "ARN de la máquina de estados a ejecutar."
  type        = string
}

variable "enabled" {
  description = "Si la regla está activa. false = el pipeline solo se ejecuta a mano."
  type        = bool
}

variable "tags" {
  description = "Etiquetas comunes aplicadas a todos los recursos."
  type        = map(string)
}
