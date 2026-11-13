"""Fixtures de los tests post-despliegue (marcador `cloud`).

Se ejecutan con `python scripts/testing/run_cloud_tests.py` y se saltan si no
hay credenciales en `.env.credentials` o en el entorno. Los nombres se derivan
igual que en Terraform: <proyecto>-<entorno> (variable LAB_NAME_PREFIX).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.aws.aws_session import get_client

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "src" / "contracts"


@pytest.fixture(scope="session")
def aws():
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        pytest.skip("Sin credenciales AWS (.env.credentials)")
    return get_client


@pytest.fixture(scope="session")
def names(aws) -> dict[str, str]:
    prefix = os.environ.get("LAB_NAME_PREFIX", "lab2-etl-dev")
    account = aws("sts").get_caller_identity()["Account"]
    return {
        "prefix": prefix,
        "bucket": os.environ.get("LAB_BUCKET", f"{prefix}-{account}-lake"),
        "database": prefix.replace("-", "_"),
    }


@pytest.fixture(scope="session")
def contracts() -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CONTRACTS_DIR.glob("*.json"))
    }
