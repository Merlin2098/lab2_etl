"""Prueba de punta a punta del pipeline con boto3.

1. Dispara una ejecución:
   --upload  genera un lote y lo sube a bronze/ (EventBridge arranca el pipeline)
   --file    sube un CSV existente tal cual (no lo regenera)
   --start   arranca la máquina de estados a mano (regla desactivada o reintento)
   (sin flag) usa la última ejecución existente
2. Sigue la ejecución de Step Functions paso a paso hasta que termina.
3. Verifica los resultados: Parquet en silver/ y gold/, tablas del Data Catalog
   iguales a los contratos, y KPIs de gold con valores coherentes.

Uso:
    uv run python scripts/check_pipeline.py --upload
    uv run python scripts/check_pipeline.py --file data/envios_2026-11-12.csv
    uv run python scripts/check_pipeline.py --start
    uv run python scripts/check_pipeline.py            # solo verificar la última ejecución

Sale con código 0 si todo está bien y 1 si algo falla.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACTS_DIR = REPO_ROOT / "src" / "contracts"
TABLES = ("silver_envios", "gold_desempeno_rutas")


# --- utilidades -----------------------------------------------------------


def ok(message: str) -> None:
    print(f"  [OK]    {message}")


def fail(message: str) -> None:
    print(f"  [FALLA] {message}")


def load_contract(table: str) -> dict:
    return json.loads((CONTRACTS_DIR / f"{table}.json").read_text(encoding="utf-8"))


def column_diff(
    actual: list[tuple[str, str]], expected: list[tuple[str, str]]
) -> list[str]:
    """Diferencias legibles entre columnas del catálogo y del contrato."""
    if actual == expected:
        return []
    problems = []
    for name, type_ in expected:
        if (name, type_) not in actual:
            found = dict(actual).get(name)
            problems.append(
                f"falta {name} {type_}"
                if found is None
                else f"{name}: catálogo={found}, contrato={type_}"
            )
    extra = [name for name, _ in actual if name not in dict(expected)]
    problems += [f"sobra {name} (no está en el contrato)" for name in extra]
    if not problems:
        problems.append("mismas columnas, distinto orden")
    return problems


# --- pasos ----------------------------------------------------------------


def find_state_machine(sfn, prefix: str) -> str:
    name = f"{prefix}-pipeline"
    for page in sfn.get_paginator("list_state_machines").paginate():
        for machine in page["stateMachines"]:
            if machine["name"] == name:
                return machine["stateMachineArn"]
    raise SystemExit(f"No existe la máquina de estados {name}. ¿Se aplicó Terraform?")


def upload_batch(bucket: str, rows: int, batch_date: date) -> None:
    from scripts.generate_envios_csv import build_batch, upload, write_csv

    out = REPO_ROOT / "data" / f"envios_{batch_date.isoformat()}.csv"
    records = build_batch(rows, batch_date, days=14, seed=42)
    write_csv(records, out)
    print(f"  {len(records)} filas -> {upload(out, bucket, batch_date)}")


def ingest_date_from_name(path: Path, default: date) -> date:
    """envios_2026-11-12.csv -> 2026-11-12; si el nombre no trae fecha, `default`."""
    try:
        return date.fromisoformat(path.stem.removeprefix("envios_"))
    except ValueError:
        return default


def upload_file(bucket: str, path: Path, batch_date: date) -> None:
    """Sube un CSV existente sin modificarlo."""
    from scripts.generate_envios_csv import upload

    if not path.is_file():
        raise SystemExit(f"No existe el archivo {path}")
    rows = sum(1 for _ in path.open(encoding="utf-8")) - 1
    print(f"  {rows} filas de {path.name} -> {upload(path, bucket, batch_date)}")


def wait_for_new_execution(sfn, machine_arn: str, since: datetime, wait_s: int) -> str:
    """Espera a que EventBridge arranque una ejecución posterior a `since`."""
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        executions = sfn.list_executions(stateMachineArn=machine_arn, maxResults=5)
        for execution in executions["executions"]:
            if execution["startDate"] >= since:
                return execution["executionArn"]
        time.sleep(5)
    raise SystemExit(
        f"Ninguna ejecución arrancó en {wait_s}s tras la subida. Revisa que la regla "
        "de EventBridge esté ENABLED (enable_event_trigger) o usa --start."
    )


def current_state(sfn, execution_arn: str) -> str | None:
    history = sfn.get_execution_history(
        executionArn=execution_arn, reverseOrder=True, maxResults=25
    )
    for event in history["events"]:
        details = event.get("stateEnteredEventDetails")
        if details:
            return details["name"]
    return None


def follow_execution(sfn, execution_arn: str, poll_s: int, timeout_s: int) -> dict:
    """Muestra cada paso nuevo hasta que la ejecución termina."""
    started = time.monotonic()
    last_state = None
    while True:
        execution = sfn.describe_execution(executionArn=execution_arn)
        state = current_state(sfn, execution_arn)
        elapsed = int(time.monotonic() - started)
        if state and state != last_state:
            print(f"  [{elapsed // 60:02d}:{elapsed % 60:02d}] {state}")
            last_state = state
        if execution["status"] != "RUNNING":
            return execution
        if elapsed > timeout_s:
            raise SystemExit(f"La ejecución sigue corriendo tras {timeout_s}s.")
        time.sleep(poll_s)


def check_outputs(s3, bucket: str) -> bool:
    good = True
    for table in TABLES:
        prefix = load_contract(table)["s3_prefix"]
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        parquet = [
            o for o in response.get("Contents", []) if o["Key"].endswith(".parquet")
        ]
        if parquet:
            ok(f"s3://{bucket}/{prefix}: {len(parquet)} archivo(s) Parquet")
        else:
            fail(f"s3://{bucket}/{prefix}: sin archivos Parquet")
            good = False
    return good


def check_catalog(glue, database: str) -> bool:
    good = True
    for table in TABLES:
        expected = [(c["name"], c["type"]) for c in load_contract(table)["columns"]]
        try:
            columns = glue.get_table(DatabaseName=database, Name=table)["Table"][
                "StorageDescriptor"
            ]["Columns"]
        except glue.exceptions.EntityNotFoundException:
            fail(f"{database}.{table}: no existe (¿corrió el crawler?)")
            good = False
            continue
        problems = column_diff([(c["Name"], c["Type"]) for c in columns], expected)
        if problems:
            fail(f"{database}.{table} difiere del contrato: {'; '.join(problems)}")
            good = False
        else:
            ok(f"{database}.{table}: {len(expected)} columnas iguales al contrato")
    return good


def check_gold_kpis(s3, bucket: str) -> bool:
    import pandas as pd

    prefix = load_contract("gold_desempeno_rutas")["s3_prefix"]
    keys = [
        o["Key"]
        for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
        if o["Key"].endswith(".parquet")
    ]
    if not keys:
        fail("gold sin datos para revisar KPIs")
        return False

    gold = pd.concat(
        pd.read_parquet(io.BytesIO(s3.get_object(Bucket=bucket, Key=k)["Body"].read()))
        for k in keys
    )
    otd = gold["otd_pct"].dropna().astype(float)
    good = len(gold) > 0 and otd.between(0, 100).all()
    (ok if good else fail)(
        f"gold: {len(gold)} filas, OTD entre {otd.min():.1f}% y {otd.max():.1f}%"
    )

    totals = gold.groupby(["origen", "destino"])[
        ["envios_entregados", "envios_a_tiempo"]
    ].sum()
    totals["otd_pct"] = 100 * totals["envios_a_tiempo"] / totals["envios_entregados"]
    print("\n  OTD por ruta (peor primero):")
    print(totals.sort_values("otd_pct").head(5).round(1).to_string(), "\n")
    return good


# --- main -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prueba de punta a punta del pipeline."
    )
    trigger = parser.add_mutually_exclusive_group()
    trigger.add_argument(
        "--upload", action="store_true", help="Subir un lote nuevo a bronze/"
    )
    trigger.add_argument(
        "--file", type=Path, help="Subir un CSV existente tal cual a bronze/"
    )
    trigger.add_argument(
        "--start", action="store_true", help="Arrancar la máquina de estados a mano"
    )
    parser.add_argument(
        "--prefix", default=os.environ.get("LAB_NAME_PREFIX", "lab2-etl-dev")
    )
    parser.add_argument("--bucket", default=os.environ.get("LAB_BUCKET"))
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--poll", type=int, default=15, help="Segundos entre consultas")
    parser.add_argument(
        "--timeout", type=int, default=1800, help="Máximo de espera en segundos"
    )
    args = parser.parse_args()

    import boto3
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env.credentials")
    account = boto3.client("sts").get_caller_identity()["Account"]
    bucket = args.bucket or f"{args.prefix}-{account}-lake"
    database = args.prefix.replace("-", "_")
    sfn, s3, glue = (
        boto3.client("stepfunctions"),
        boto3.client("s3"),
        boto3.client("glue"),
    )

    print(f"Pipeline {args.prefix} | bucket {bucket} | base {database}\n")
    machine_arn = find_state_machine(sfn, args.prefix)

    print("1. Ejecución")
    if args.upload or args.file:
        since = datetime.now(timezone.utc) - timedelta(seconds=5)
        if args.file:
            batch_date = ingest_date_from_name(args.file, args.date)
            upload_file(bucket, args.file, batch_date)
        else:
            upload_batch(bucket, args.rows, args.date)
        execution_arn = wait_for_new_execution(sfn, machine_arn, since, wait_s=120)
        print("  EventBridge arrancó la ejecución")
    elif args.start:
        execution_arn = sfn.start_execution(stateMachineArn=machine_arn)["executionArn"]
        print("  Ejecución arrancada a mano")
    else:
        executions = sfn.list_executions(stateMachineArn=machine_arn, maxResults=1)
        if not executions["executions"]:
            raise SystemExit("No hay ejecuciones todavía: usa --upload o --start.")
        execution_arn = executions["executions"][0]["executionArn"]
        print("  Usando la última ejecución")
    print(f"  {execution_arn}\n")

    print("2. Seguimiento")
    execution = follow_execution(sfn, execution_arn, args.poll, args.timeout)
    duration = execution["stopDate"] - execution["startDate"]
    if execution["status"] != "SUCCEEDED":
        fail(f"{execution['status']} tras {duration}")
        print(f"  error: {execution.get('error')}\n  causa: {execution.get('cause')}")
        return 1
    ok(f"SUCCEEDED en {duration}\n")

    print("3. Resultados")
    results = [
        check_outputs(s3, bucket),
        check_catalog(glue, database),
        check_gold_kpis(s3, bucket),
    ]
    if all(results):
        print("Pipeline OK")
        return 0
    print("Pipeline con problemas: revisa los [FALLA] de arriba")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
