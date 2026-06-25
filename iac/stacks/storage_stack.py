"""Storage stack: the data-lake foundation.

KMS-encrypted raw + curated S3 zones with lifecycle tiering, a central server-access-log
bucket, and an Athena query-results bucket.

DEA-C01:
  D2 - data-lake zoning (raw vs curated), lifecycle/tiering, Athena results location
  D4 - encryption at rest (KMS), in transit (SSL-only), block public access, access logging
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_kms as kms,
)
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Single KMS key for the lake. RETAIN in production; DESTROY here for cheap teardown.
        self.data_key = kms.Key(
            self,
            "DataKey",
            alias="alias/dea-c01-lake",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Central server-access-log target (D4 audit). Uses S3-managed encryption so the S3
        # log-delivery group can write without extra KMS grants. Does not log to itself.
        self.logs_bucket = s3.Bucket(
            self,
            "AccessLogsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[s3.LifecycleRule(expiration=Duration.days(90))],
        )

        # Settings shared by the two data zones.
        common = dict(
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.data_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,   # study project: allow clean destroy
            auto_delete_objects=True,
            server_access_logs_bucket=self.logs_bucket,
        )

        # Raw landing zone: reproducible, so tier down then expire to save cost.
        self.raw_bucket = s3.Bucket(
            self,
            "RawBucket",
            server_access_logs_prefix="raw/",
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),
                        )
                    ],
                    expiration=Duration.days(90),
                )
            ],
            **common,
        )

        # Curated zone: cleaned, partitioned Parquet. Kept (no expiry) — it's the product.
        self.curated_bucket = s3.Bucket(
            self,
            "CuratedBucket",
            server_access_logs_prefix="curated/",
            **common,
        )

        # Athena writes query results here (D2/D3). Results are disposable -> short expiry.
        self.athena_results_bucket = s3.Bucket(
            self,
            "AthenaResultsBucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.data_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_bucket=self.logs_bucket,
            server_access_logs_prefix="athena-results/",
            lifecycle_rules=[s3.LifecycleRule(expiration=Duration.days(7))],
        )
