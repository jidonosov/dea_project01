"""Glue PySpark ETL: raw -> curated (partitioned Parquet) with a Data Quality gate.

DEA-C01: D1 (transformation, Parquet, partitioning), D3 (data quality).
Tier 3 (AGENTS.md): transform logic carries silent data-quality-corruption risk — human review.

This is a STUB. Fill in `transform()` for your dataset and the DQ ruleset, then test it in
tests/test_glue_transform.py with chispa before deploying.
"""
import sys

# Guarded so the file imports under plain pytest (no Spark/Glue runtime present).
try:
    from awsglue.utils import getResolvedOptions  # type: ignore
    from awsglue.context import GlueContext  # type: ignore
    from pyspark.context import SparkContext  # type: ignore
    _GLUE_RUNTIME = True
except ImportError:  # local / CI without Spark
    _GLUE_RUNTIME = False


def transform(df):
    """Pure transform — unit-testable without a Glue runtime.

    TODO: real logic. Placeholder partitions by ingestion date and drops null keys.
    """
    from pyspark.sql import functions as F

    return (
        df.dropna(subset=["id"])
        .withColumn("year", F.year("event_time"))
        .withColumn("month", F.month("event_time"))
        .withColumn("day", F.dayofmonth("event_time"))
    )


# Example Glue Data Quality ruleset (DQDL). Attach as a job step / EvaluateDataQuality.
DATA_QUALITY_RULESET = """
Rules = [
    IsComplete "id",
    ColumnValues "amount" >= 0,
    RowCount > 0
]
"""


def main():
    args = getResolvedOptions(sys.argv, ["RAW_PATH", "CURATED_PATH", "DATABASE"])
    sc = SparkContext()
    glue_ctx = GlueContext(sc)
    spark = glue_ctx.spark_session

    raw = spark.read.json(args["RAW_PATH"])
    curated = transform(raw)

    (
        curated.write.mode("append")
        .partitionBy("year", "month", "day")
        .parquet(args["CURATED_PATH"])
    )


if __name__ == "__main__" and _GLUE_RUNTIME:
    main()
