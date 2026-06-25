from datetime import datetime

from src.common.partitioning import s3_partition_path


def test_partition_path_zero_pads_month_and_day():
    path = s3_partition_path("curated/", datetime(2026, 6, 5))
    assert path == "curated/year=2026/month=06/day=05"


def test_partition_path_strips_trailing_slash():
    assert s3_partition_path("a/b/", datetime(2026, 12, 31)).startswith("a/b/year=2026")
