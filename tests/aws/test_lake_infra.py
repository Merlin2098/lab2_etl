"""Valida la infraestructura desplegada contra los guardrails de AGENTS.md."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.cloud


def test_bucket_is_private_encrypted_unversioned_and_emits_events(aws, names) -> None:
    s3 = aws("s3")
    bucket = names["bucket"]

    block = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
    assert all(block.values())

    rules = s3.get_bucket_encryption(Bucket=bucket)[
        "ServerSideEncryptionConfiguration"
    ]["Rules"]
    assert rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"

    # Un bucket que nunca tuvo versionado no devuelve "Status".
    assert "Status" not in s3.get_bucket_versioning(Bucket=bucket)

    assert "EventBridgeConfiguration" in s3.get_bucket_notification_configuration(
        Bucket=bucket
    )


def test_glue_jobs_use_lab_capacity(aws, names) -> None:
    glue = aws("glue")

    for key in ("bronze-to-silver", "silver-to-gold"):
        job = glue.get_job(JobName=f"{names['prefix']}-{key}")["Job"]
        assert job["GlueVersion"] == "5.1"
        assert job["WorkerType"] == "G.1X"
        assert job["NumberOfWorkers"] == 2
        assert job["Timeout"] == 10
        assert job["DefaultArguments"]["--TempDir"] == f"s3://{names['bucket']}/tmp/"


def test_crawlers_update_schema_in_catalog(aws, names) -> None:
    glue = aws("glue")

    for layer in ("silver", "gold"):
        crawler = glue.get_crawler(Name=f"{names['prefix']}-{layer}-crawler")["Crawler"]
        assert crawler["DatabaseName"] == names["database"]
        assert crawler["TablePrefix"] == f"{layer}_"
        assert crawler["SchemaChangePolicy"]["UpdateBehavior"] == "UPDATE_IN_DATABASE"
        assert "Schedule" not in crawler


def test_log_groups_have_retention(aws, names) -> None:
    logs = aws("logs")
    expected = [
        f"/aws-glue/{names['prefix']}/error",
        f"/aws-glue/{names['prefix']}/output",
        f"/aws/vendedlogs/states/{names['prefix']}-pipeline",
    ]

    for name in expected:
        groups = logs.describe_log_groups(logGroupNamePrefix=name)["logGroups"]
        group = next(g for g in groups if g["logGroupName"] == name)
        assert group.get("retentionInDays"), f"{name} sin retención"


def test_event_rule_only_watches_bronze(aws, names) -> None:
    rule = aws("events").describe_rule(Name=f"{names['prefix']}-bronze-upload")
    pattern = json.loads(rule["EventPattern"])

    assert rule["State"] == "ENABLED"
    assert pattern["detail"]["bucket"]["name"] == [names["bucket"]]
    # Sin este filtro, las escrituras en silver/ y gold/ dispararían el pipeline en bucle.
    assert pattern["detail"]["object"]["key"] == [{"prefix": "bronze/envios/"}]


def test_pipeline_state_machine_exists(aws, names) -> None:
    machines = aws("stepfunctions").list_state_machines()["stateMachines"]
    assert f"{names['prefix']}-pipeline" in {m["name"] for m in machines}
