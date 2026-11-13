# Dispara el pipeline cuando llega un CSV nuevo a bronze/envios/.
# El filtro de prefijo es obligatorio: los jobs escriben silver/ y gold/ en el
# mismo bucket y, sin él, cada escritura volvería a disparar el pipeline.

resource "aws_cloudwatch_event_rule" "bronze_upload" {
  name        = "${var.name_prefix}-bronze-upload"
  description = "Lab 2: CSV nuevo en bronze/envios/ -> pipeline Step Functions."
  state       = var.enabled ? "ENABLED" : "DISABLED"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [var.bucket_name] }
      object = { key = [{ prefix = var.trigger_prefix }] }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "pipeline" {
  rule     = aws_cloudwatch_event_rule.bronze_upload.name
  arn      = var.state_machine_arn
  role_arn = aws_iam_role.events.arn
}

# --- IAM: EventBridge solo puede arrancar esta máquina de estados ---

data "aws_iam_policy_document" "events_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "events" {
  name               = "${var.name_prefix}-events-role"
  assume_role_policy = data.aws_iam_policy_document.events_assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "start_pipeline" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [var.state_machine_arn]
  }
}

resource "aws_iam_role_policy" "start_pipeline" {
  name   = "${var.name_prefix}-start-pipeline"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.start_pipeline.json
}
