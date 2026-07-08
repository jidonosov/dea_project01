"""Data generator Lambda: emits realistic-synthetic e-commerce order events to Firehose.

DEA-C01: D1 (ingestion). Tier 2 (AGENTS.md) -- covered by unit tests (tests/test_generator.py).

Why synthetic-but-realistic instead of a real public dataset (educational choice):
  This is a teaching artifact on a tight budget. Synthetic data stays in MB (no Athena/Glue
  scan-cost surprises), carries no licensing/egress cost, and -- the real reason -- lets us
  inject the exact messiness that makes the downstream pipeline *teach*:
    - at-least-once DUPLICATES (Firehose can deliver a record more than once) and NULL keys,
      which curated_etl.transform() must clean (dedup + drop). Emitted always.
    - values that VIOLATE the Glue Data Quality ruleset (negative amount / unknown category),
      so you can watch the DQ gate fail the job and refuse to write curated. Opt-in, so the
      happy-path walkthrough still produces clean curated data.
  Swap make_record()'s body for a real feed later; keep the order_id / event_time contract that
  the transform and Data Quality rules depend on.

Schema (raw JSON -> Firehose -> raw zone):
  order_id: uuid str · event_time: ISO-8601 str · customer_id: str · category: str
  quantity: int · unit_price: float · amount: float (= quantity*unit_price, the masked column)
  currency: str · country: str · payment_method: str
"""
import json
import os
import random
import uuid
from datetime import datetime, timezone

# Guarded so the pure record-building logic imports under pytest without boto3 installed
# (the Lambda runtime provides boto3; the base dev deps stay light). Same pattern as curated_etl.
try:
    import boto3
except ImportError:  # local / CI without boto3
    boto3 = None

STREAM = os.environ.get("DELIVERY_STREAM", "dea-c01-raw")

# Realistic-but-small domains. Categories MUST match the DQ ruleset in curated_etl.py.
CATEGORIES = ["electronics", "books", "grocery", "clothing", "home"]
COUNTRIES = ["US", "GB", "DE", "FR", "BR"]
PAYMENT_METHODS = ["card", "paypal", "gift_card", "bank_transfer"]

# Firehose put_record_batch hard limits: 500 records AND 4 MB per call. Chunk to stay under them.
_FIREHOSE_MAX_BATCH = 500


def make_record(now: datetime = None) -> dict:
    """One clean, valid e-commerce order event. Pure -> unit-testable without AWS."""
    now = now or datetime.now(timezone.utc)
    quantity = random.randint(1, 5)
    unit_price = round(random.uniform(2.0, 400.0), 2)
    return {
        "order_id": str(uuid.uuid4()),
        "event_time": now.isoformat(),
        "customer_id": f"cust_{random.randint(0, 9999):04d}",
        "category": random.choice(CATEGORIES),
        "quantity": quantity,
        "unit_price": unit_price,
        # amount is derived, so it's internally consistent -- the DQ rule `amount >= 0` then
        # asserts a real invariant rather than checking a standalone random number.
        "amount": round(quantity * unit_price, 2),
        "currency": "USD",
        "country": random.choice(COUNTRIES),
        "payment_method": random.choice(PAYMENT_METHODS),
    }


def build_batch(
    count: int,
    *,
    dup_rate: float = 0.05,
    null_rate: float = 0.02,
    inject_dq_violations: bool = False,
) -> list:
    """Build a batch of records with the messiness described in the module docstring.

    dup_rate / null_rate exercise transform() (dedup + drop) and keep DQ passing.
    inject_dq_violations (opt-in) plants rows that FAIL the DQ ruleset to demo the gate.
    """
    records = [make_record() for _ in range(count)]

    # At-least-once duplicates: exact repeats (same order_id) so transform()'s dedup has work to do.
    for _ in range(int(count * dup_rate)):
        records.append(dict(random.choice(records)))

    # Unkeyable rows: a null order_id or event_time can't be deduped or partitioned, so transform()
    # DROPS them before curated. This is cleaning, not a quality failure -- DQ still passes.
    for r in records:
        if random.random() < null_rate:
            r[random.choice(["order_id", "event_time"])] = None

    # Opt-in quality violations: a negative total (refund miscoded) or an unknown category. These
    # trip `ColumnValues "amount" >= 0` / the category allow-list, so the DQ gate fails the job.
    if inject_dq_violations:
        for r in random.sample(records, max(1, int(count * 0.03))):
            if random.random() < 0.5:
                r["amount"] = -abs(r["amount"])
            else:
                r["category"] = "UNKNOWN"

    return records


def handler(event, context):
    event = event or {}
    count = int(event.get("count", 100))
    # Toggle bad data via the event ({"inject_dq_violations": true}) or the env var. Off by default.
    inject = event.get("inject_dq_violations")
    if inject is None:
        inject = os.environ.get("INJECT_DQ_VIOLATIONS", "false").lower() == "true"

    records = build_batch(count, inject_dq_violations=bool(inject))
    # newline-delimited JSON so the raw zone is one object per line (what the ETL's .json() expects).
    payload = [{"Data": json.dumps(r).encode() + b"\n"} for r in records]

    firehose = boto3.client("firehose")
    sent = 0
    for i in range(0, len(payload), _FIREHOSE_MAX_BATCH):
        chunk = payload[i : i + _FIREHOSE_MAX_BATCH]
        firehose.put_record_batch(DeliveryStreamName=STREAM, Records=chunk)
        sent += len(chunk)

    return {"sent": sent, "stream": STREAM, "dq_violations_injected": bool(inject)}
