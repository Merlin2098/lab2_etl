"""Tras una ejecución del pipeline: las tablas que registraron los crawlers
deben coincidir (columnas, orden y tipos) con los contratos.

Si falla después de un cambio de esquema, lo habitual es que el crawler no se
haya ejecutado o que el contrato y el SQL hayan divergido.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.cloud


@pytest.mark.parametrize("table", ["silver_envios", "gold_desempeno_rutas"])
def test_catalog_table_matches_contract(aws, names, contracts, table) -> None:
    glue = aws("glue")
    try:
        response = glue.get_table(DatabaseName=names["database"], Name=table)
    except glue.exceptions.EntityNotFoundException:
        pytest.fail(f"{table} no existe: ejecuta el pipeline (sube un CSV) primero")

    columns = response["Table"]["StorageDescriptor"]["Columns"]
    actual = [(c["Name"], c["Type"]) for c in columns]
    expected = [(c["name"], c["type"]) for c in contracts[table]["columns"]]

    assert actual == expected
