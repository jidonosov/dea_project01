"""Catalog + Glue stack: Glue database, crawler, and a PySpark ETL job.

DEA-C01: D1 (Glue ETL, crawlers, Parquet/partitioning) and D2 (Data Catalog).
The ETL script in src/glue/curated_etl.py is uploaded as a CDK asset.

Lake Formation note (D4): once the account's "use only IAM access control" defaults are
turned OFF (so the curated table can be column-masked -- see governance_stack.py), the Data
Catalog is LF-governed. From that point a Glue role's IAM policy is NOT enough to create a
table: the crawler needs an explicit Lake Formation grant on the database, or it fails with
"Insufficient Lake Formation permission(s) on database". So we grant it below. This is the
exact trade-off LF forces: fine-grained governance means every writer needs a real grant too.
"""
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_kms as kms,
    aws_iam as iam,
    aws_glue as glue,
    aws_lakeformation as lakeformation,
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

        # Curated crawler: catalogs the ETL's partitioned Parquet output so Athena has a *governed*
        # table to query. This is the table the analyst actually reads (governance_stack.py registers
        # the curated location with Lake Formation and column-masks this table). Without it, curated
        # exists only as S3 files with no catalog entry -- nothing to SELECT and nothing to mask.
        #
        # It reads the same Parquet the ETL writes (partitioned year=/month=/day=), so the crawler
        # picks up y/m/d as partition keys automatically -- no manual partition management.
        # NOTE: run it AFTER the ETL has written curated data (see the runbook), or it finds nothing.
        curated_crawler = glue.CfnCrawler(
            self,
            "CuratedCrawler",
            role=role.role_arn,
            database_name=self.database_name,
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    glue.CfnCrawler.S3TargetProperty(path=f"s3://{curated_bucket.bucket_name}/")
                ]
            ),
        )
        curated_crawler.add_dependency(db)

        # Lake Formation grant so the crawler role can write tables into the LF-governed database.
        # Needed only because the account's IAM-only default was disabled (see module docstring);
        # with the default on, IAMAllowedPrincipals would cover this and the grant would be moot.
        #   - Database: CREATE_TABLE so the crawler can add tables; DESCRIBE/ALTER so re-crawls can
        #     see and evolve the database. (The crawler owns the tables it creates, but ALTER on
        #     the table wildcard lets it update schemas of tables from a previous run.)
        # The deploy identity must be a Lake Formation admin for this grant to apply (runbook M1).
        glue_db_grant = lakeformation.CfnPermissions(
            self,
            "GlueRoleDatabaseGrant",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=role.role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                database_resource=lakeformation.CfnPermissions.DatabaseResourceProperty(
                    catalog_id=self.account,
                    name=self.database_name,
                )
            ),
            permissions=["CREATE_TABLE", "ALTER", "DESCRIBE"],
        )
        glue_table_grant = lakeformation.CfnPermissions(
            self,
            "GlueRoleTableGrant",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=role.role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                table_resource=lakeformation.CfnPermissions.TableResourceProperty(
                    catalog_id=self.account,
                    database_name=self.database_name,
                    table_wildcard={},  # tables don't exist yet -> grant on all (present + future)
                )
            ),
            permissions=["ALTER", "DESCRIBE", "DROP", "INSERT", "SELECT"],
        )
        # Grants reference the database by name; make the ordering on its creation explicit.
        glue_db_grant.add_dependency(db)
        glue_table_grant.add_dependency(db)

        self.etl_job_name = etl_job.name
        self.crawler_name = crawler.ref
        self.curated_crawler_name = curated_crawler.ref
        # Exposed so the governance stack can grant this role DATA_LOCATION_ACCESS on the (LF-
        # registered) curated location -- required for the curated crawler to create a table there.
        self.glue_role_arn = role.role_arn
