"""Glue transform tests. Skipped unless pyspark is installed (kept out of the base deps to
stay light). Locally: `pip install pyspark` then run pytest to exercise these.
"""
import pytest

pyspark = pytest.importorskip("pyspark")


def _spark():
    from pyspark.sql import SparkSession

    return SparkSession.builder.master("local[1]").appName("test").getOrCreate()


def test_transform_cleans_dedups_and_partitions():
    from src.glue.curated_etl import transform

    spark = _spark()
    # event_time is a string on purpose: exercises the ISO-8601 -> timestamp cast path.
    rows = [
        ("1", "2026-06-25T10:00:00", 10.0, "A"),    # valid; earliest event for id 1
        ("1", "2026-06-25T12:00:00", 99.0, "a"),    # duplicate id -> dropped (later event)
        (None, "2026-06-25T11:00:00", 5.0, "b"),    # null id -> dropped
        ("2", "2026-06-26T09:00:00", 7.5, " c "),   # valid; category needs trim/lower
    ]
    df = spark.createDataFrame(rows, ["id", "event_time", "amount", "category"])

    out = transform(df)
    got = {r["id"]: r for r in out.orderBy("id").collect()}
    spark.stop()

    # null id + duplicate id removed
    assert set(got) == {"1", "2"}
    # partition columns present and derived from event_time (not the raw path)
    assert {"year", "month", "day"}.issubset(out.columns)
    assert (got["1"]["year"], got["1"]["month"], got["1"]["day"]) == (2026, 6, 25)
    # dedup kept the EARLIEST event for id 1 (amount 10.0, not the later 99.0)
    assert got["1"]["amount"] == 10.0
    # category normalized (lowercased + trimmed)
    assert got["1"]["category"] == "a"
    assert got["2"]["category"] == "c"


def test_transform_is_idempotent_on_already_typed_timestamp():
    """Handed an already-typed timestamp column, the dtype guard must not re-cast to null."""
    from pyspark.sql import functions as F

    from src.glue.curated_etl import transform

    spark = _spark()
    df = spark.createDataFrame(
        [("1", "2026-06-25T10:00:00", 10.0, "a")],
        ["id", "event_time", "amount", "category"],
    ).withColumn("event_time", F.to_timestamp("event_time"))

    out = transform(df).collect()
    spark.stop()

    assert len(out) == 1
    assert (out[0]["year"], out[0]["month"], out[0]["day"]) == (2026, 6, 25)
