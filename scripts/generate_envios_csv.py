"""Simula el export diario de envíos del TMS de Andes Freight (empresa ficticia).

Genera un CSV con "suciedad" controlada (duplicados, IDs vacíos, texto
inconsistente) y, con --upload, lo sube a
s3://<bucket>/bronze/envios/ingest_date=<fecha>/envios.csv, lo que dispara el
pipeline (EventBridge -> Step Functions).

Cada fecha genera datos distintos pero reproducibles (semilla + fecha).

Uso:
    uv run python scripts/generate_envios_csv.py --rows 1000
    uv run python scripts/generate_envios_csv.py --date 2026-11-13 --to 2026-11-14
    uv run python scripts/generate_envios_csv.py --rows 1000 --upload   # LAB_BUCKET o --bucket
"""

from __future__ import annotations

import argparse
import csv
import os
import random
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

HEADER = [
    "envio_id",
    "cliente_id",
    "fecha_despacho",
    "fecha_entrega_prometida",
    "fecha_entrega",
    "origen",
    "destino",
    "tipo_carga",
    "peso_kg",
    "tarifa_pen",
    "estado",
]

# Ruta Lima <-> destino: (días de tránsito comprometidos, tarifa PEN por kg).
ROUTES = {
    "Arequipa": (2, 0.45),
    "Trujillo": (1, 0.35),
    "Chiclayo": (2, 0.40),
    "Piura": (3, 0.50),
    "Cusco": (3, 0.60),
}

# Tipo de carga: (peso relativo, recargo sobre la tarifa, prob. de entrega tarde).
# La carga refrigerada llega tarde más seguido: es la historia del cambio en vivo.
CARGO_TYPES = {
    "GENERAL": (0.70, 1.00, 0.08),
    "REFRIGERADA": (0.20, 1.35, 0.22),
    "PELIGROSA": (0.10, 1.60, 0.10),
}

STATUSES = {"ENTREGADO": 0.85, "EN_TRANSITO": 0.10, "CANCELADO": 0.05}

BASE_FEE_PEN = 80.0
DUPLICATE_RATE = 0.03
EMPTY_ID_RATE = 0.01
MESSY_TEXT_RATE = 0.20


def _rng(seed: int, batch_date: date, purpose: str) -> random.Random:
    """Generador reproducible y distinto para cada fecha de lote."""
    return random.Random(f"{seed}:{batch_date.isoformat()}:{purpose}")


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _messy(rng: random.Random, value: str) -> str:
    """Ensucia un texto: mayúsculas/minúsculas mezcladas y espacios sobrantes."""
    if rng.random() >= MESSY_TEXT_RATE:
        return value
    variant = rng.choice([value.lower(), value.upper(), value.title()])
    return f"{' ' * rng.randint(0, 2)}{variant}{' ' * rng.randint(0, 2)}"


def generate_rows(
    rows: int, batch_date: date, days: int, seed: int
) -> list[dict[str, str]]:
    """Genera `rows` envíos limpios despachados en los `days` días previos a `batch_date`.

    `batch_date` es la fecha del export: solo hay entregas hasta el día anterior.
    """
    rng = _rng(seed, batch_date, "envios")
    records = []

    for i in range(1, rows + 1):
        city = rng.choice(list(ROUTES))
        origen, destino = ("Lima", city) if rng.random() < 0.6 else (city, "Lima")
        transit_days, rate_per_kg = ROUTES[city]

        tipo_carga = _pick(rng, {k: v[0] for k, v in CARGO_TYPES.items()})
        _, surcharge, late_prob = CARGO_TYPES[tipo_carga]

        fecha_despacho = batch_date - timedelta(days=rng.randint(1, days))
        fecha_prometida = fecha_despacho + timedelta(days=transit_days)
        estado = _pick(rng, STATUSES)

        fecha_entrega = ""
        if estado == "ENTREGADO":
            delay = rng.randint(1, 3) if rng.random() < late_prob else 0
            entrega = fecha_prometida + timedelta(days=delay)
            if entrega < batch_date:
                fecha_entrega = entrega.isoformat()
            else:
                estado = "EN_TRANSITO"  # aún no llega a la fecha del export

        peso_kg = round(rng.uniform(50, 5000), 2)
        tarifa_pen = round(BASE_FEE_PEN + peso_kg * rate_per_kg * surcharge, 2)

        records.append(
            {
                "envio_id": f"GR-{batch_date:%Y%m%d}-{i:06d}",
                "cliente_id": f"CLI-{rng.randint(1, 60):03d}",
                "fecha_despacho": fecha_despacho.isoformat(),
                "fecha_entrega_prometida": fecha_prometida.isoformat(),
                "fecha_entrega": fecha_entrega,
                "origen": origen,
                "destino": destino,
                "tipo_carga": tipo_carga,
                "peso_kg": f"{peso_kg:.2f}",
                "tarifa_pen": f"{tarifa_pen:.2f}",
                "estado": estado,
            }
        )

    return records


def add_dirt(
    records: list[dict[str, str]], seed: int, batch_date: date
) -> list[dict[str, str]]:
    """Agrega los problemas típicos del export: duplicados, IDs vacíos, texto sucio."""
    rng = _rng(seed, batch_date, "suciedad")
    dirty = []

    for record in records:
        row = dict(record)
        if rng.random() < EMPTY_ID_RATE:
            row["envio_id"] = ""
        for column in ("origen", "destino", "tipo_carga", "estado"):
            row[column] = _messy(rng, row[column])
        dirty.append(row)

    duplicates = rng.sample(dirty, k=int(len(dirty) * DUPLICATE_RATE))
    dirty.extend(dict(row) for row in duplicates)
    rng.shuffle(dirty)
    return dirty


def write_csv(records: list[dict[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(records)
    return path


def upload(path: Path, bucket: str, batch_date: date) -> str:
    import boto3
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env.credentials")
    key = f"bronze/envios/ingest_date={batch_date.isoformat()}/envios.csv"
    boto3.client("s3").upload_file(str(path), bucket, key)
    return f"s3://{bucket}/{key}"


def batch_dates(start: date, end: date | None) -> list[date]:
    """Fechas de lote de `start` a `end` (inclusive); solo `start` si no hay `end`."""
    end = end or start
    if end < start:
        raise ValueError(f"--to ({end}) es anterior a --date ({start})")
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


def build_batch(rows: int, batch_date: date, days: int, seed: int) -> list[dict]:
    """Lote completo de un día: envíos + suciedad controlada."""
    return add_dirt(generate_rows(rows, batch_date, days, seed), seed, batch_date)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera el CSV diario de envíos del TMS (uno por fecha)."
    )
    parser.add_argument("--rows", type=int, default=1000, help="Envíos por día")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="Fecha del lote, o inicio del rango con --to (AAAA-MM-DD)",
    )
    parser.add_argument(
        "--to",
        type=date.fromisoformat,
        default=None,
        help="Fin del rango (inclusive): genera un archivo por día",
    )
    parser.add_argument(
        "--days", type=int, default=14, help="Días hacia atrás de fecha de despacho"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None, help="Solo para una fecha")
    parser.add_argument(
        "--upload", action="store_true", help="Subir a bronze/ (dispara el pipeline)"
    )
    parser.add_argument("--bucket", default=os.environ.get("LAB_BUCKET"))
    args = parser.parse_args()

    try:
        dates = batch_dates(args.date, args.to)
    except ValueError as exc:
        parser.error(str(exc))
    if args.out and len(dates) > 1:
        parser.error("--out solo se puede usar con una fecha (sin --to)")
    if args.upload and not args.bucket:
        parser.error("--upload requiere --bucket o la variable LAB_BUCKET")

    for batch_date in dates:
        out = args.out or REPO_ROOT / "data" / f"envios_{batch_date.isoformat()}.csv"
        records = build_batch(args.rows, batch_date, args.days, args.seed)
        write_csv(records, out)
        print(f"{batch_date}: {len(records)} filas escritas en {out}")
        if args.upload:
            # Cada archivo dispara una ejecución del pipeline. Si llegan juntas,
            # Step Functions reintenta los jobs (ConcurrentRunsExceeded).
            print(f"{batch_date}: subido a {upload(out, args.bucket, batch_date)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
