"""Data generator Lambda: emits sample records to Kinesis Firehose.

DEA-C01: D1 (ingestion). Tier 2 (AGENTS.md) — covered by unit tests.
Swap make_record() for your real dataset. Firehose delivery stream name comes from env.
"""
import json
import os
import random
import uuid
from datetime import datetime, timezone

import boto3

firehose = boto3.client("firehose")
STREAM = os.environ.get("DELIVERY_STREAM", "dea-c01-raw")


def make_record() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "event_time": datetime.now(timezone.utc).isoformat(),
        "amount": round(random.uniform(1, 500), 2),
        "category": random.choice(["a", "b", "c"]),
    }


def handler(event, context):
    batch = int((event or {}).get("count", 100))
    records = [{"Data": json.dumps(make_record()).encode() + b"\n"} for _ in range(batch)]
    firehose.put_record_batch(DeliveryStreamName=STREAM, Records=records)
    return {"sent": batch, "stream": STREAM}
