from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from scripts.generate_envios_csv import (
    HEADER,
    batch_dates,
    build_batch,
    generate_rows,
    write_csv,
)

BATCH_DATE = date(2026, 11, 10)
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "src" / "contracts"


def _batch(
    rows: int = 1000, seed: int = 42, batch_date: date = BATCH_DATE
) -> list[dict[str, str]]:
    return build_batch(rows, batch_date, days=14, seed=seed)


def test_header_matches_silver_contract_columns() -> None:
    import json

    contract = json.loads(
        (CONTRACTS_DIR / "silver_envios.json").read_text(encoding="utf-8")
    )
    assert HEADER == [c["name"] for c in contract["columns"]]


def test_same_seed_is_reproducible() -> None:
    assert _batch(seed=7) == _batch(seed=7)
    assert _batch(seed=7) != _batch(seed=8)


def test_each_date_produces_different_data() -> None:
    def strip_ids(records: list[dict[str, str]]) -> list[tuple]:
        return [tuple(v for k, v in r.items() if k != "envio_id") for r in records]

    day_13 = _batch(batch_date=date(2026, 11, 13))
    day_14 = _batch(batch_date=date(2026, 11, 14))

    assert strip_ids(day_13) != strip_ids(day_14)
    ids_13 = {r["envio_id"] for r in day_13 if r["envio_id"]}
    ids_14 = {r["envio_id"] for r in day_14 if r["envio_id"]}
    assert not ids_13 & ids_14, "los envio_id no deben repetirse entre días"


def test_no_delivery_on_or_after_export_date() -> None:
    records = generate_rows(1000, BATCH_DATE, days=14, seed=42)
    delivered = [r for r in records if r["fecha_entrega"]]

    assert all(r["fecha_entrega"] < BATCH_DATE.isoformat() for r in delivered)
    # Lo despachado ayer no puede haber llegado (tránsito mínimo 1 día).
    yesterday = date(2026, 11, 9).isoformat()
    assert all(
        r["estado"] != "ENTREGADO" for r in records if r["fecha_despacho"] == yesterday
    )


def test_batch_dates_range_is_inclusive() -> None:
    assert batch_dates(date(2026, 11, 13), None) == [date(2026, 11, 13)]
    assert batch_dates(date(2026, 11, 13), date(2026, 11, 14)) == [
        date(2026, 11, 13),
        date(2026, 11, 14),
    ]
    with pytest.raises(ValueError):
        batch_dates(date(2026, 11, 14), date(2026, 11, 13))


def test_batch_includes_controlled_dirt() -> None:
    records = _batch()
    ids = Counter(r["envio_id"] for r in records if r["envio_id"])

    assert len(records) == 1000 + int(1000 * 0.03)
    assert any(count > 1 for count in ids.values()), "debe haber envio_id duplicados"
    assert any(r["envio_id"] == "" for r in records), "debe haber envio_id vacíos"
    assert any(r["estado"] != r["estado"].strip().upper() for r in records), (
        "texto sucio"
    )


def test_clean_rows_follow_business_rules() -> None:
    records = generate_rows(1000, BATCH_DATE, days=14, seed=42)
    delivered = [r for r in records if r["estado"] == "ENTREGADO"]
    late = [r for r in delivered if r["fecha_entrega"] > r["fecha_entrega_prometida"]]

    assert all(r["fecha_entrega"] == "" for r in records if r["estado"] != "ENTREGADO")
    assert all(r["fecha_despacho"] < BATCH_DATE.isoformat() for r in records)
    assert 0 < len(late) < len(delivered), "el OTD no debe ser 0 % ni 100 %"
    assert {r["tipo_carga"] for r in records} == {"GENERAL", "REFRIGERADA", "PELIGROSA"}


def test_write_csv_roundtrip(tmp_path: Path) -> None:
    records = _batch(rows=50)
    path = write_csv(records, tmp_path / "envios.csv")

    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == HEADER
        assert list(reader) == records
