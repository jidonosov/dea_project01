"""Governance stack: Lake Formation fine-grained access over the curated zone.

DEA-C01: D4 (fine-grained permissions, governed data access).

NOTE: Lake Formation setup is order-sensitive and account-specific (you must first set a data
lake admin in the console or via CfnDataLakeSettings). The grants below are documented
placeholders — flesh them out once the database has tables. Keep this a Tier 3 file (AGENTS.md).
"""
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    # aws_lakeformation as lakeformation,  # uncomment when wiring real grants
)
from constructs import Construct


class GovernanceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        curated_bucket: s3.IBucket,
        database_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.curated_bucket = curated_bucket
        self.database_name = database_name

        # TODO (D4): register the curated bucket as a Lake Formation resource, then grant
        # column-/row-level SELECT to an analyst IAM principal. Sketch:
        #
        # lakeformation.CfnResource(self, "CuratedLocation",
        #     resource_arn=curated_bucket.bucket_arn, use_service_linked_role=True)
        # lakeformation.CfnPermissions(self, "AnalystSelect",
        #     data_lake_principal=...DataLakePrincipalProperty(
        #         data_lake_principal_identifier="<analyst-role-arn>"),
        #     resource=...ResourceProperty(
        #         table_resource=...TableResourceProperty(
        #             database_name=database_name, name="<table>")),
        #     permissions=["SELECT"])
