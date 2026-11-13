output "bucket_name" {
  description = "Nombre del bucket del lake."
  value       = aws_s3_bucket.lake.bucket
}

output "bucket_arn" {
  description = "ARN del bucket del lake."
  value       = aws_s3_bucket.lake.arn
}

output "resource_arn" {
  description = "ARN del recurso principal del módulo (bucket)."
  value       = aws_s3_bucket.lake.arn
}

output "code_object_keys" {
  description = "Claves S3 del código subido para los Glue jobs."
  value       = sort(keys(aws_s3_object.code))
}
