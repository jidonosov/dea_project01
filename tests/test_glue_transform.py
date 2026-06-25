"""Glue transform tests. Skipped unless pyspark is installed (kept out of the base deps to
stay light). Locally: `pip install pyspark chispa` then run pytest to exercise these.
"""
import pytest

pyspark = pytest.importorskip("pyspark")


def test_transform_drops_null_ids_and_adds_partitions():
    from pyspark.sql import SparkSession
    from src.glue.curated_etl import transform

    spark = SparkSession.builder.master("local[1]").appName("test").getOrCreate()
    df = spark.createDataFrame(
        [("1", "2026-06-25T10:00:00", 10.0), (None, "2026-06-25T11:00:00", 5.0)],
        ["id", "event_time", "amount"],
    ).withColumn("event_time", __import__("pyspark.sql.functions", fromlist=["to_timestamp"]).to_timestamp("event_time"))

    out = transform(df)
    assert out.count() == 1                       # null id dropped
    assert {"year", "month", "day"}.issubset(out.columns)
    spark.stop()
