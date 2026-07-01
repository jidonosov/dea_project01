"""Ingestion stack: generator Lambda -> Kinesis Data Firehose -> S3 raw zone.

DEA-C01:
  D1 - streaming ingestion (Firehose buffering/delivery), a Lambda producer, and
       partitioned landing layout in the raw zone.
  D3 - delivery-failure visibility via CloudWatch Logs; cost-bounded buffering.
  D4 - least-privilege Firehose role; writes into the KMS-encrypted raw bucket.

Why Firehose (direct-to-S3) over the alternatives, in THIS project's context:
  * vs. Kinesis Data Streams + a consumer Lambda: Firehose is fully managed for the
    "land raw events into S3" job -- no shards to size, no consumer code to write,
    scale, or pay for. Data Streams only earns its extra complexity when you need
    sub-second latency, replay, or several independent consumers of one stream -- none
    of which a batch study lakehouse needs.
  * vs. a Firehose transform Lambda / dynamic partitioning / JSON->Parquet on ingest:
    kept OFF on purpose. The downstream Glue ETL already owns JSON->Parquet conversion
    and cleaning; doing it twice would add per-record Firehose cost and blur which
    component is responsible for shaping data. Raw stays raw (immutable JSON); curated
    is where transformation happens.
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_kms as kms,
    aws_iam as iam,
    aws_kinesisfirehose as firehose,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct


class IngestionStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        raw_bucket: s3.IBucket,
        data_key: kms.IKey,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudWatch log group for Firehose delivery errors. Short retention: these are
        # operational breadcrumbs, not data we keep (D3 monitoring, kept cheap).
        log_group = logs.LogGroup(
            self,
            "FirehoseLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        log_stream = logs.LogStream(self, "FirehoseLogStream", log_group=log_group)

        # Least-privilege role Firehose assumes to write to the raw bucket + use the KMS
        # key + emit its own error logs. Firehose needs GenerateDataKey/Decrypt because the
        # raw bucket enforces KMS encryption on every object it writes.
        firehose_role = iam.Role(
            self,
            "FirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
        )
        raw_bucket.grant_read_write(firehose_role)
        data_key.grant_encrypt_decrypt(firehose_role)
        log_group.grant_write(firehose_role)

        # DirectPut: the generator Lambda calls PutRecordBatch straight into Firehose
        # (no Kinesis Data Stream in front). Firehose buffers, GZIPs, and lands JSON in S3.
        self.delivery_stream = firehose.CfnDeliveryStream(
            self,
            "RawDeliveryStream",
            delivery_stream_name="dea-c01-raw",
            delivery_stream_type="DirectPut",
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=raw_bucket.bucket_arn,
                role_arn=firehose_role.role_arn,
                # Hive-style time partitions so the Glue crawler discovers year/month/day
                # automatically and Athena can partition-prune (D2). Firehose fills the
                # !{timestamp:...} tokens from delivery time.
                prefix="events/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/",
                error_output_prefix="errors/!{firehose:error-output-type}/",
                # GZIP: cheaper S3 storage + fewer bytes for Glue/Athena to scan; Spark and
                # Athena read gzipped JSON transparently, so it costs nothing downstream.
                compression_format="GZIP",
                # Buffer flush: whichever comes first. 60s / 5 MB keeps latency low for a
                # micro-batch demo while avoiding a flood of tiny objects. Bigger buffers =
                # fewer, larger files = cheaper to scan, at the cost of freshness.
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=60,
                    size_in_m_bs=5,
                ),
                cloud_watch_logging_options=firehose.CfnDeliveryStream.CloudWatchLoggingOptionsProperty(
                    enabled=True,
                    log_group_name=log_group.log_group_name,
                    log_stream_name=log_stream.log_stream_name,
                ),
            ),
        )
        self.delivery_stream.node.add_dependency(firehose_role)

        # Generator Lambda (the record producer). boto3 ships in the Lambda runtime, so the
        # handler in src/lambda/generator needs no bundled dependencies.
        self.generator = lambda_.Function(
            self,
            "GeneratorFn",
            function_name="dea-c01-generator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset("src/lambda/generator"),
            timeout=Duration.seconds(60),
            memory_size=128,
            environment={"DELIVERY_STREAM": self.delivery_stream.ref},
        )
        # Only permission the producer needs: push batches into this one stream.
        self.generator.add_to_role_policy(
            iam.PolicyStatement(
                actions=["firehose:PutRecordBatch", "firehose:PutRecord"],
                resources=[self.delivery_stream.attr_arn],
            )
        )
