from __future__ import annotations

from scripts.check_pipeline import column_diff

CONTRACT = [
    ("fecha_despacho", "date"),
    ("origen", "string"),
    ("envios_total", "bigint"),
]


def test_equal_columns_have_no_diff() -> None:
    assert column_diff(list(CONTRACT), CONTRACT) == []


def test_reports_missing_extra_and_type_changes() -> None:
    catalog = [
        ("fecha_despacho", "date"),
        ("origen", "varchar"),
        ("tipo_carga", "string"),
    ]

    problems = column_diff(catalog, CONTRACT)

    assert "origen: catálogo=varchar, contrato=string" in problems
    assert "falta envios_total bigint" in problems
    assert "sobra tipo_carga (no está en el contrato)" in problems


def test_reports_order_only_difference() -> None:
    assert column_diff(list(reversed(CONTRACT)), CONTRACT) == [
        "mismas columnas, distinto orden"
    ]
