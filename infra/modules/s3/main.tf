# Bucket único del lake: bronze/, silver/, gold/, scripts/ y tmp/.

resource "aws_s3_bucket" "lake" {
  bucket        = var.bucket_name
  force_destroy = true # lab desechable: destroy elimina también los datos
  tags          = var.tags
}

# Versionado deshabilitado de forma explícita (bucket nuevo, nunca versionado).
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket = aws_s3_bucket.lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Envía los eventos del bucket (Object Created, etc.) a EventBridge. El filtro
# de qué eventos disparan el pipeline está en el módulo eventbridge.
resource "aws_s3_bucket_notification" "lake" {
  bucket      = aws_s3_bucket.lake.id
  eventbridge = true
}

# Código de los Glue jobs: scripts .py, SQL y contratos. Se suben todos los
# archivos que existan en src/; etag fuerza la re-subida cuando cambian.
locals {
  job_scripts = {
    for f in fileset("${var.src_dir}/jobs", "*.py") :
    "scripts/${f}" => "${var.src_dir}/jobs/${f}" if f != "__init__.py"
  }
  sql_files = {
    for f in fileset("${var.src_dir}/transformations", "*.sql") :
    "scripts/sql/${f}" => "${var.src_dir}/transformations/${f}"
  }
  contracts = {
    for f in fileset("${var.src_dir}/contracts", "*.json") :
    "scripts/contracts/${f}" => "${var.src_dir}/contracts/${f}"
  }
  code_objects = merge(local.job_scripts, local.sql_files, local.contracts)
}

resource "aws_s3_object" "code" {
  for_each = local.code_objects

  bucket = aws_s3_bucket.lake.id
  key    = each.key
  source = each.value
  etag   = filemd5(each.value)
  tags   = var.tags
}
