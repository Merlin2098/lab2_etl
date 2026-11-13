# Raíz: solo nombres, etiquetas y llamadas a módulos (un módulo por servicio).

data "aws_caller_identity" "current" {}

locals {
  name_prefix = lower(replace("${var.project_name}-${var.environment}", "_", "-"))
  bucket_name = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-lake"

  common_tags = merge(
    var.tags,
    {
      Project     = var.project_name
      Environment = var.environment
      Owner       = var.owner
      ManagedBy   = "Terraform"
      CostCenter  = var.cost_center
    }
  )
}

module "s3" {
  source = "./modules/s3"

  bucket_name = local.bucket_name
  src_dir     = "${path.root}/../src"
  tags        = local.common_tags
}

module "cloudwatch" {
  source = "./modules/cloudwatch"

  name_prefix    = local.name_prefix
  retention_days = var.log_retention_days
  tags           = local.common_tags
}

module "iam" {
  source = "./modules/iam"

  name_prefix = local.name_prefix
  bucket_arn  = module.s3.bucket_arn
  tags        = local.common_tags
}

module "glue" {
  source = "./modules/glue"

  name_prefix       = local.name_prefix
  bucket_name       = module.s3.bucket_name
  role_arn          = module.iam.role_arn
  log_group_prefix  = module.cloudwatch.log_group_prefix
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout_minutes   = var.glue_timeout_minutes
  tags              = local.common_tags
}

module "stepfunctions" {
  source = "./modules/stepfunctions"

  name_prefix              = local.name_prefix
  job_names                = module.glue.job_names
  job_arns                 = module.glue.job_arns
  crawler_names            = module.glue.crawler_names
  crawler_arns             = module.glue.crawler_arns
  log_group_arn            = module.cloudwatch.pipeline_log_group_arn
  crawler_poll_seconds     = var.crawler_poll_seconds
  pipeline_timeout_seconds = var.pipeline_timeout_seconds
  tags                     = local.common_tags
}

module "eventbridge" {
  source = "./modules/eventbridge"

  name_prefix       = local.name_prefix
  bucket_name       = module.s3.bucket_name
  trigger_prefix    = "bronze/envios/"
  state_machine_arn = module.stepfunctions.state_machine_arn
  enabled           = var.enable_event_trigger
  tags              = local.common_tags
}
