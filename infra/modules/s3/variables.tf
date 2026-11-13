variable "bucket_name" {
  description = "Nombre global del bucket del lake."
  type        = string
}

variable "src_dir" {
  description = "Ruta local a src/ (jobs, transformations, contracts) que se sube a scripts/."
  type        = string
}

variable "tags" {
  description = "Etiquetas comunes aplicadas a todos los recursos."
  type        = map(string)
}
