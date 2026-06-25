"""Storage stack: KMS-encrypted raw + curated S3 zones with lifecycle tiering.

DEA-C01: D2 (data lake zoning, lifecycle) and D4 (encryption at rest, SSL-only, block public).
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

        # Single KMS key for the lake. RETAIN in real life; DESTROY here for cheap teardown.
        self.data_key = kms.Key(
            self,
            "DataKey",
            alias="alias/dea-c01-lake",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        common = dict(
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.data_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,   # study project: allow clean destroy
            auto_delete_objects=True,
        )

        self.raw_bucket = s3.Bucket(
            self,
            "RawBucket",
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),
                        )
                    ],
                    expiration=Duration.days(90),  # raw is reproducible; expire to save cost
                )
            ],
            **common,
        )

        self.curated_bucket = s3.Bucket(
            self,
            "CuratedBucket",
            **common,
        )
