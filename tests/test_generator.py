"""Unit tests for the generator Lambda's pure record-building logic (no AWS / Firehose).

The handler lives under src/lambda/, and `lambda` is a Python keyword, so it can't be imported
with a normal dotted import -- load it by file path instead. The boto3 client is created lazily
inside handler(), so importing the module here needs no AWS credentials.
"""
import importlib.util
import pathlib
import random

import pytest

_HANDLER_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "src" / "lambda" / "generator" / "handler.py"
)


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generator_handler", _HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_record_shape_and_derived_amount(gen):
    random.seed(0)
    r = gen.make_record()
    # every field the raw schema / transform / DQ rules rely on is present
    assert set(r) >= {
        "order_id", "event_time", "customer_id", "category",
        "quantity", "unit_price", "amount", "currency", "country", "payment_method",
    }
    # amount is derived from quantity * unit_price -> the DQ invariant is real, not coincidental
    assert r["amount"] == round(r["quantity"] * r["unit_price"], 2)
    # category stays inside the DQ allow-list
    assert r["category"] in gen.CATEGORIES


def test_clean_batch_passes_quality_expectations(gen):
    random.seed(1)
    records = gen.build_batch(200, dup_rate=0.0, null_rate=0.0, inject_dq_violations=False)
    assert len(records) == 200
    # a clean batch must satisfy what the DQ ruleset asserts downstream
    assert all(r["amount"] >= 0 for r in records)
    assert all(r["quantity"] > 0 for r in records)
    assert all(r["category"] in gen.CATEGORIES for r in records)
    assert all(r["order_id"] and r["event_time"] for r in records)


def test_duplicates_and_nulls_are_injected_for_the_transform_to_clean(gen):
    random.seed(2)
    records = gen.build_batch(200, dup_rate=0.2, null_rate=0.1)
    # duplicates: more rows than the base count, and at least one repeated order_id
    assert len(records) > 200
    ids = [r["order_id"] for r in records if r["order_id"] is not None]
    assert len(ids) != len(set(ids))  # a duplicate order_id exists -> transform() dedups it
    # nulls: at least one unkeyable row exists -> transform() drops it
    assert any(r["order_id"] is None or r["event_time"] is None for r in records)


def test_opt_in_violations_break_the_dq_ruleset(gen):
    random.seed(3)
    records = gen.build_batch(200, dup_rate=0.0, null_rate=0.0, inject_dq_violations=True)
    # at least one row must violate a DQ rule (negative amount OR unknown category)
    assert any(r["amount"] < 0 or r["category"] not in gen.CATEGORIES for r in records)


def test_violations_off_by_default(gen):
    random.seed(4)
    records = gen.build_batch(200, dup_rate=0.0, null_rate=0.0)
    assert all(r["amount"] >= 0 and r["category"] in gen.CATEGORIES for r in records)
