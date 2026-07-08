"""Glue transform tests. Skipped unless pyspark is installed (kept out of the base deps to
stay light). Locally: `pip install pyspark` then run pytest to exercise these.
"""
import pytest

pyspark = pytest.importorskip("pyspark")


def _spark():
    from pyspark.sql import SparkSession

    return SparkSession.builder.master("local[1]").appName("test").getOrCreate()


_COLS = ["order_id", "event_time", "customer_id", "category", "quantity", "unit_price", "amount"]


def test_transform_cleans_dedups_and_partitions():
    from src.glue.curated_etl import transform

    spark = _spark()
    # event_time is a string on purpose: exercises the ISO-8601 -> timestamp cast path.
    rows = [
        # order_id, event_time, customer_id, category, quantity, unit_price, amount
        ("1", "2026-06-25T10:00:00", "c1", "Electronics", 2, 5.0, 10.0),   # earliest for order 1
        ("1", "2026-06-25T12:00:00", "c1", "electronics", 2, 5.0, 99.0),   # dup order_id -> dropped
        (None, "2026-06-25T11:00:00", "c2", "books", 1, 5.0, 5.0),         # null order_id -> dropped
        ("2", "2026-06-26T09:00:00", "c3", " grocery ", 3, 2.5, 7.5),      # category needs trim/lower
    ]
    df = spark.createDataFrame(rows, _COLS)

    out = transform(df)
    got = {r["order_id"]: r for r in out.orderBy("order_id").collect()}
    spark.stop()

    # null order_id + duplicate order_id removed
    assert set(got) == {"1", "2"}
    # partition columns present and derived from event_time (not the raw path)
    assert {"year", "month", "day"}.issubset(out.columns)
    assert (got["1"]["year"], got["1"]["month"], got["1"]["day"]) == (2026, 6, 25)
    # dedup kept the EARLIEST event for order 1 (amount 10.0, not the later 99.0)
    assert got["1"]["amount"] == 10.0
    # category normalized (lowercased + trimmed)
    assert got["1"]["category"] == "electronics"
    assert got["2"]["category"] == "grocery"


def test_transform_is_idempotent_on_already_typed_timestamp():
    """Handed an already-typed timestamp column, the dtype guard must not re-cast to null."""
    from pyspark.sql import functions as F

    from src.glue.curated_etl import transform

    spark = _spark()
    df = spark.createDataFrame(
        [("1", "2026-06-25T10:00:00", "c1", "electronics", 2, 5.0, 10.0)],
        _COLS,
    ).withColumn("event_time", F.to_timestamp("event_time"))

    out = transform(df).collect()
    spark.stop()

    assert len(out) == 1
    assert (out[0]["year"], out[0]["month"], out[0]["day"]) == (2026, 6, 25)
