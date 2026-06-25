"""Catalog + Glue stack: Glue database, crawler, and a PySpark ETL job.

DEA-C01: D1 (Glue ETL, crawlers, Parquet/partitioning) and D2 (Data Catalog).
The ETL script in src/glue/curated_etl.py is uploaded as a CDK asset.
"""
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_kms as kms,
    aws_iam as iam,
    aws_glue as glue,
    aws_s3_assets as s3_assets,
)
from constructs import Construct


class CatalogGlueStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        raw_bucket: s3.IBucket,
        curated_bucket: s3.IBucket,
        data_key: kms.IKey,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.database_name = "dea_c01_lakehouse"
        db = glue.CfnDatabase(
            self,
            "Database",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(name=self.database_name),
        )

        # Least-privilege role for Glue: read raw, write curated, use the KMS key.
        role = iam.Role(
            self,
            "GlueRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
            ],
        )
        raw_bucket.grant_read(role)
        curated_bucket.grant_read_write(role)
        data_key.grant_encrypt_decrypt(role)

        # Upload the PySpark script as an asset and point the job at it.
        script = s3_assets.Asset(self, "EtlScript", path="src/glue/curated_etl.py")
        script.grant_read(role)

        etl_job = glue.CfnJob(
            self,
            "CuratedEtlJob",
            name="dea-c01-curated-etl",
            role=role.role_arn,
            glue_version="4.0",
            number_of_workers=2,        # minimum — keep cost down
            worker_type="G.1X",
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                python_version="3",
                script_location=f"s3://{script.s3_bucket_name}/{script.s3_object_key}",
            ),
            default_arguments={
                "--job-language": "python",
                "--RAW_PATH": f"s3://{raw_bucket.bucket_name}/",
                "--CURATED_PATH": f"s3://{curated_bucket.bucket_name}/",
                "--DATABASE": self.database_name,
                "--enable-metrics": "true",
            },
        )

        crawler = glue.CfnCrawler(
            self,
            "RawCrawler",
            role=role.role_arn,
            database_name=self.database_name,
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[glue.CfnCrawler.S3TargetProperty(path=f"s3://{raw_bucket.bucket_name}/")]
            ),
        )
        crawler.add_dependency(db)

        self.etl_job_name = etl_job.name
        self.crawler_name = crawler.ref
