"""Glue PySpark ETL: raw -> curated (partitioned Parquet) with a Data Quality gate.

DEA-C01:
  D1 - transformation, type normalization, dedup for idempotent writes, Parquet +
       year/month/day partitioning.
  D3 - Glue Data Quality gate that fails the job before bad data reaches curated.
Tier 3 (AGENTS.md): transform logic carries silent data-quality-corruption risk -> human review.

Design split (kept deliberately, per CLAUDE.md's educational-intent convention):
  transform() SHAPES the data (types, dedup, partitions); the DATA_QUALITY_RULESET
  VALIDATES it. Keeping "make it well-formed" separate from "assert it's correct" means a
  failing rule points at a real data problem, not at transform logic quietly papering over it.

Input schema (from the generator Lambda -> Firehose raw JSON):
  id: string (uuid) · event_time: string (ISO-8601) · amount: double · category: string
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
    """Pure transform -- unit-testable without a Glue runtime.

    Shapes raw records into the curated form: real timestamp, deduplicated by id,
    normalized types/values, and year/month/day partition columns. Validation of the
    result is the DATA_QUALITY_RULESET's job, not this function's.
    """
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    # Raw JSON delivers event_time as an ISO-8601 *string*. Normalize to a real timestamp so
    # curated has proper types (not everything-is-string) and partitions can be derived.
    # Guarded on dtype so the function is idempotent if handed an already-typed column.
    if dict(df.dtypes).get("event_time") == "string":
        df = df.withColumn("event_time", F.to_timestamp("event_time"))

    return (
        df
        # No id or no event_time -> the row can't be keyed or partitioned. Drop it.
        .where(F.col("id").isNotNull() & F.col("event_time").isNotNull())
        # Firehose delivery is at-least-once, so the raw zone may contain duplicate ids.
        # Dedup (keep the earliest event per id) makes the curated write idempotent: a
        # re-run over the same raw data won't double-count. This is the DEA-C01 answer to
        # "how do you get exactly-once semantics on top of at-least-once ingestion".
        .withColumn(
            "_rn",
            F.row_number().over(Window.partitionBy("id").orderBy(F.col("event_time").asc())),
        )
        .where(F.col("_rn") == 1)
        .drop("_rn")
        # Type + value normalization only (no validation here -- that's the DQ ruleset).
        .withColumn("amount", F.col("amount").cast("double"))
        .withColumn("category", F.lower(F.trim(F.col("category"))))
        # Partition columns for the curated Parquet layout. Integer y/m/d so Athena can
        # partition-prune with plain numeric predicates (see analysis/exploratory.sql).
        .withColumn("year", F.year("event_time"))
        .withColumn("month", F.month("event_time"))
        .withColumn("day", F.dayofmonth("event_time"))
    )


# Glue Data Quality ruleset (DQDL). Each rule asserts something transform() is supposed to
# guarantee or that the source promises -- so a failure is a genuine data problem.
DATA_QUALITY_RULESET = """
Rules = [
    IsComplete "id",
    IsUnique "id",
    IsComplete "event_time",
    ColumnValues "amount" >= 0,
    ColumnValues "category" in ["a", "b", "c"],
    RowCount > 0
]
"""


def main():
    args = getResolvedOptions(sys.argv, ["RAW_PATH", "CURATED_PATH", "DATABASE"])
    sc = SparkContext()
    glue_ctx = GlueContext(sc)
    spark = glue_ctx.spark_session

    # recursiveFileLookup: read the raw JSON as flat records and IGNORE the Firehose
    # year=/month=/day= path partitions, so transform() derives partitions fresh from
    # event_time instead of inheriting duplicate partition columns from the path.
    # NOTE: this reads the whole raw zone every run. A production job would use Glue job
    # bookmarks (or read only new partitions) to process incrementally and cut cost (D1/D3).
    raw = spark.read.option("recursiveFileLookup", "true").json(args["RAW_PATH"])
    curated = transform(raw)

    # Data Quality gate (D3): evaluate the ruleset and fail the job on any failed rule, so
    # bad data never lands in the curated zone. Imported here (not at module top) so the file
    # still imports under plain pytest without the Glue DQ libs installed.
    from awsglue.dynamicframe import DynamicFrame  # type: ignore
    from awsgluedq.transforms import EvaluateDataQuality  # type: ignore

    dyf = DynamicFrame.fromDF(curated, glue_ctx, "curated")
    # .apply() returns a rule-level outcomes DynamicFrame (columns: Rule, Outcome,
    # FailureReason, EvaluatedMetrics). Any Outcome == "Failed" means the data violated a rule.
    dq_results = EvaluateDataQuality.apply(
        frame=dyf,
        ruleset=DATA_QUALITY_RULESET,
        publishing_options={
            "dataQualityEvaluationContext": "curated_etl",
            "enableDataQualityCloudWatchMetrics": True,
            "enableDataQualityResultsPublishing": True,
        },
    )
    failed = dq_results.toDF().where("Outcome = 'Failed'")
    if failed.count() > 0:
        failed.show(truncate=False)
        raise RuntimeError("Data Quality gate failed -- not writing to curated zone.")

    (
        curated.write.mode("append")
        .partitionBy("year", "month", "day")
        .parquet(args["CURATED_PATH"])
    )


if __name__ == "__main__" and _GLUE_RUNTIME:
    main()
