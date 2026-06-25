"""Pure-logic helpers (Tier 2 — CI-gated). No AWS imports, fully unit-testable."""
from datetime import datetime


def s3_partition_path(prefix: str, ts: datetime) -> str:
    """Hive-style year/month/day partition path used by the curated zone."""
    return f"{prefix.rstrip('/')}/year={ts.year}/month={ts.month:02d}/day={ts.day:02d}"
