# Rol único para Glue jobs y crawlers.

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${var.name_prefix}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
  tags               = var.tags
}

# Policy gestionada de Glue: Data Catalog y logs en /aws-glue/*.
resource "aws_iam_role_policy_attachment" "glue_service_role" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Acceso acotado al bucket del lake (origen y destino de jobs, origen de crawlers).
data "aws_iam_policy_document" "lake_access" {
  statement {
    sid       = "ListLakeBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
  }

  statement {
    sid = "ReadWriteLakeObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "lake_access" {
  name   = "${var.name_prefix}-lake-access"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.lake_access.json
}
