#!/usr/bin/env python3
"""CDK entry point for the DEA-C01 serverless lakehouse.

Account/region come from your AWS CLI profile via CDK_DEFAULT_*.
Every resource is tagged project=dea-c01 for cost tracking and least-privilege scoping.
"""
import aws_cdk as cdk

from iac.stacks.storage_stack import StorageStack
from iac.stacks.catalog_glue_stack import CatalogGlueStack
from iac.stacks.orchestration_stack import OrchestrationStack
from iac.stacks.governance_stack import GovernanceStack

PREFIX = "dea-c01"

app = cdk.App()
env = cdk.Environment()  # resolves from CDK_DEFAULT_ACCOUNT / CDK_DEFAULT_REGION

storage = StorageStack(app, f"{PREFIX}-storage", env=env)

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

GovernanceStack(
    app,
    f"{PREFIX}-governance",
    curated_bucket=storage.curated_bucket,
    database_name=catalog.database_name,
    env=env,
)

cdk.Tags.of(app).add("project", PREFIX)
app.synth()
