"""Chequeo local contrato <-> SQL.

Replica en segundos lo que validan los Glue jobs antes de escribir: las
columnas del `select` final de cada SQL deben coincidir, en nombre y orden, con
su contrato. Si se cambia el SQL sin el contrato (o al revés), falla aquí antes
de gastar una corrida de Glue.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# SQL -> contrato que valida su salida (igual que en infra/modules/glue/jobs.tf).
PAIRS = {
    "bronze_to_silver.sql": "silver_envios.json",
    "silver_to_gold.sql": "gold_desempeno_rutas.json",
}

GLUE_TYPE = re.compile(
    r"^(string|date|bigint|int|double|boolean|timestamp|decimal\(\d+,\d+\))$"
)


def _contract(name: str) -> dict:
    return json.loads((SRC / "contracts" / name).read_text(encoding="utf-8"))


def _final_select_columns(sql: str) -> list[str]:
    """Nombres de salida del último `select ... from` de nivel superior."""
    sql = re.sub(r"--[^\n]*", "", sql)
    start = list(re.finditer(r"\bselect\b", sql, re.IGNORECASE))[-1].end()

    items, depth, current = [], 0, ""
    for match in re.finditer(r"\(|\)|,|\bfrom\b|[^(),]", sql[start:], re.IGNORECASE):
        token = match.group(0)
        if token.lower() == "from" and depth == 0:
            break
        if token == "," and depth == 0:
            items.append(current)
            current = ""
            continue
        depth += {"(": 1, ")": -1}.get(token, 0)
        current += token
    items.append(current)

    names = []
    for item in items:
        alias = re.search(r"\bas\s+(\w+)\s*$", item.strip(), re.IGNORECASE)
        names.append(alias.group(1) if alias else item.strip())
    return names


@pytest.mark.parametrize("contract_file", sorted(set(PAIRS.values())))
def test_contract_structure(contract_file: str) -> None:
    contract = _contract(contract_file)

    assert contract["table"] == contract_file.removesuffix(".json")
    assert contract["s3_prefix"].endswith("/")
    assert set(contract["primary_key"]) <= {c["name"] for c in contract["columns"]}
    for column in contract["columns"]:
        assert GLUE_TYPE.match(column["type"]), f"tipo inválido: {column}"
        assert column["comment"], f"columna sin descripción: {column['name']}"


@pytest.mark.parametrize(("sql_file", "contract_file"), sorted(PAIRS.items()))
def test_sql_output_matches_contract(sql_file: str, contract_file: str) -> None:
    sql = (SRC / "transformations" / sql_file).read_text(encoding="utf-8")
    expected = [c["name"] for c in _contract(contract_file)["columns"]]

    assert _final_select_columns(sql) == expected
