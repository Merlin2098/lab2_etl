# Orquestación del pipeline: job bronze->silver, crawler silver,
# job silver->gold, crawler gold.
#
# - Los jobs usan la integración optimizada glue:startJobRun.sync (espera nativa).
# - Los crawlers no tienen integración .sync: se arrancan con aws-sdk:glue:startCrawler
#   y se espera con un ciclo Wait -> GetCrawler -> Choice.

locals {
  # Paso siguiente al terminar cada crawler.
  crawler_next = {
    Silver = "SilverToGold"
    Gold   = "PipelineSucceeded"
  }

  catch_all = [{
    ErrorEquals = ["States.ALL"]
    ResultPath  = "$.error"
    Next        = "PipelineFailed"
  }]

  # Si llegan dos archivos seguidos, el segundo run choca con el primero
  # (concurrencia máxima 1). Se reintenta en lugar de fallar.
  retry_job = [{
    ErrorEquals     = ["Glue.ConcurrentRunsExceededException"]
    IntervalSeconds = 60
    MaxAttempts     = 5
    BackoffRate     = 1.5
  }]

  job_states = {
    BronzeToSilver = {
      Type       = "Task"
      Resource   = "arn:aws:states:::glue:startJobRun.sync"
      Parameters = { JobName = var.job_names["bronze-to-silver"] }
      ResultPath = "$.bronze_to_silver"
      Retry      = local.retry_job
      Catch      = local.catch_all
      Next       = "StartSilverCrawler"
    }
    SilverToGold = {
      Type       = "Task"
      Resource   = "arn:aws:states:::glue:startJobRun.sync"
      Parameters = { JobName = var.job_names["silver-to-gold"] }
      ResultPath = "$.silver_to_gold"
      Retry      = local.retry_job
      Catch      = local.catch_all
      Next       = "StartGoldCrawler"
    }
  }

  # 4 estados por crawler: Start -> Wait -> Get -> Choice (vuelve a Wait si sigue corriendo).
  crawler_states = merge([
    for layer, next in local.crawler_next : {
      "Start${layer}Crawler" = {
        Type       = "Task"
        Resource   = "arn:aws:states:::aws-sdk:glue:startCrawler"
        Parameters = { Name = var.crawler_names[lower(layer)] }
        ResultPath = null
        Retry = [{
          ErrorEquals     = ["Glue.CrawlerRunningException"]
          IntervalSeconds = 30
          MaxAttempts     = 6
          BackoffRate     = 1
        }]
        Catch = local.catch_all
        Next  = "Wait${layer}Crawler"
      }
      "Wait${layer}Crawler" = {
        Type    = "Wait"
        Seconds = var.crawler_poll_seconds
        Next    = "Get${layer}Crawler"
      }
      "Get${layer}Crawler" = {
        Type       = "Task"
        Resource   = "arn:aws:states:::aws-sdk:glue:getCrawler"
        Parameters = { Name = var.crawler_names[lower(layer)] }
        ResultPath = "$.${lower(layer)}_crawler"
        Catch      = local.catch_all
        Next       = "Is${layer}CrawlerReady"
      }
      "Is${layer}CrawlerReady" = {
        Type = "Choice"
        Choices = [{
          Variable     = "$.${lower(layer)}_crawler.Crawler.State"
          StringEquals = "READY"
          Next         = "Did${layer}CrawlerSucceed"
        }]
        Default = "Wait${layer}Crawler"
      }
      "Did${layer}CrawlerSucceed" = {
        Type = "Choice"
        Choices = [
          {
            # Aún no hay LastCrawl (primer crawl todavía no registrado): seguir esperando.
            Not  = { Variable = "$.${lower(layer)}_crawler.Crawler.LastCrawl.Status", IsPresent = true }
            Next = "Wait${layer}Crawler"
          },
          {
            Variable     = "$.${lower(layer)}_crawler.Crawler.LastCrawl.Status"
            StringEquals = "SUCCEEDED"
            Next         = next
          },
        ]
        Default = "PipelineFailed"
      }
    }
  ]...)

  definition = {
    Comment        = "Lab 2: bronze -> silver -> gold con crawlers del Data Catalog"
    StartAt        = "BronzeToSilver"
    TimeoutSeconds = var.pipeline_timeout_seconds
    States = merge(local.job_states, local.crawler_states, {
      PipelineSucceeded = { Type = "Succeed" }
      PipelineFailed = {
        Type  = "Fail"
        Error = "PipelineFailed"
        Cause = "Un paso falló; revisar $.error en la ejecución y los logs de Glue."
      }
    })
  }
}

resource "aws_sfn_state_machine" "pipeline" {
  name       = "${var.name_prefix}-pipeline"
  type       = "STANDARD"
  role_arn   = aws_iam_role.sfn.arn
  definition = jsonencode(local.definition)

  logging_configuration {
    log_destination        = "${var.log_group_arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = var.tags

  depends_on = [aws_iam_role_policy.sfn]
}

# --- IAM: el rol de la máquina vive aquí porque aquí se conocen sus destinos ---

data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${var.name_prefix}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid = "RunGlueJobsSync"
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]
    resources = values(var.job_arns)
  }

  statement {
    sid       = "RunAndPollCrawlers"
    actions   = ["glue:StartCrawler", "glue:GetCrawler"]
    resources = values(var.crawler_arns)
  }

  # Entrega de logs de Step Functions a CloudWatch. AWS exige Resource "*"
  # para estas acciones (no admiten ARN de recurso).
  statement {
    sid = "DeliverExecutionLogs"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${var.name_prefix}-sfn-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}
