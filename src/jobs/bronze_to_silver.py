"""Glue job bronze -> silver.

Lee el CSV crudo de bronze/envios/, aplica bronze_to_silver.sql, valida el
resultado contra el contrato silver_envios.json y escribe Parquet en silver/.
El SQL y el contrato llegan al directorio de trabajo vía --extra-files.
"""

import json
import sys

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession

args = getResolvedOptions(sys.argv, ["bucket", "sql_file", "contract_file"])
spark = SparkSession.builder.getOrCreate()
base = f"s3://{args['bucket']}"

with open(args["contract_file"], encoding="utf-8") as f:
    contract = json.load(f)
with open(args["sql_file"], encoding="utf-8") as f:
    sql = f.read()

# Todas las columnas se leen como string; los tipos los fija el SQL.
bronze = spark.read.option("header", True).csv(f"{base}/bronze/envios/")
bronze.createOrReplaceTempView("bronze_envios")
result = spark.sql(sql)

# Contrato primero: nombres, orden y tipos deben coincidir antes de escribir.
expected = [(c["name"], c["type"]) for c in contract["columns"]]
if result.dtypes != expected:
    raise ValueError(f"Salida {result.dtypes} no coincide con el contrato {expected}")

result.write.mode("overwrite").parquet(f"{base}/{contract['s3_prefix']}")
print(
    f"{contract['table']}: {result.count()} filas escritas en {contract['s3_prefix']}"
)
