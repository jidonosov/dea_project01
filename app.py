#!/usr/bin/env python3
"""CDK entry point for the DEA-C01 serverless lakehouse.

Account/region come from your AWS CLI profile via CDK_DEFAULT_*.
Every resource is tagged project=dea-c01 for cost tracking and least-privilege scoping.
"""
import aws_cdk as cdk

from iac.stacks.storage_stack import StorageStack
from iac.stacks.ingestion_stack import IngestionStack
from iac.stacks.catalog_glue_stack import CatalogGlueStack
from iac.stacks.orchestration_stack import OrchestrationStack
from iac.stacks.governance_stack import GovernanceStack

PREFIX = "dea-c01"

app = cdk.App()
env = cdk.Environment()  # resolves from CDK_DEFAULT_ACCOUNT / CDK_DEFAULT_REGION

storage = StorageStack(app, f"{PREFIX}-storage", env=env)

# Ingest: generator Lambda -> Firehose -> raw zone. Depends only on storage (raw bucket + key).
IngestionStack(
    app,
    f"{PREFIX}-ingestion",
    raw_bucket=storage.raw_bucket,
    data_key=storage.data_key,
    env=env,
)

catalog = CatalogGlueStack(
    app,
    f"{PREFIX}-catalog-glue",
    raw_bucket=storage.raw_bucket,
    curated_bucket=storage.curated_bucket,
    data_key=storage.data_key,
    env=env,
)

OrchestrationStack(
    app,
    f"{PREFIX}-orchestration",
    etl_job_name=catalog.etl_job_name,
    crawler_name=catalog.crawler_name,
    env=env,
)

governance = GovernanceStack(
    app,
    f"{PREFIX}-governance",
    curated_bucket=storage.curated_bucket,
    data_key=storage.data_key,                      # LF registration role needs kms:Decrypt
    athena_results_bucket=storage.athena_results_bucket,  # analyst reads/writes query results
    database_name=catalog.database_name,
    glue_role_arn=catalog.glue_role_arn,            # curated crawler needs DATA_LOCATION_ACCESS
    env=env,
)
# The LF grants reference the catalog's database by *name* (a plain string), so CloudFormation
# can't infer the cross-stack edge — make it explicit so the database exists before we grant on it.
governance.add_dependency(catalog)

cdk.Tags.of(app).add("project", PREFIX)
app.synth()
