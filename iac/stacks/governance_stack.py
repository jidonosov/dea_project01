"""Governance stack: Lake Formation fine-grained access over the curated zone.

DEA-C01:
  D4 - fine-grained (column-level) access control on a governed data lake, enforced at
       query time by Athena/Glue rather than by S3 bucket policy.

Why Lake Formation over plain IAM / S3 bucket policies (the exam trade-off):
  An S3 bucket/prefix policy is all-or-nothing on a *path*: a principal can read every object
  under the prefix or none of them. It can't say "this analyst may read `category` but not
  `amount`". Lake Formation grants SELECT on *catalog* tables down to the column (and row/cell)
  level, centrally, and Athena + Glue enforce those grants transparently. Column/row-level
  masking on shared tables is exactly what bucket policies can't express -- that's when LF earns
  its extra setup over the simpler IAM-only model.

Two hard realities this stack encodes (both are common DEA-C01 gotchas):

  1. Lake Formation is ORDER-SENSITIVE and needs a *data lake admin* before any grant works.
     Designating that admin is a one-time manual step (console, or CfnDataLakeSettings). We do
     NOT set CfnDataLakeSettings here on purpose: writing `admins` REPLACES the entire admin
     list rather than appending, so a bad value can lock every human (and this very deploy role)
     out of Lake Formation. Prefer the deliberate manual designation documented in the README.
     PRECONDITION: the identity that runs `cdk deploy` must already be a Lake Formation admin,
     or the grants below fail at deploy time.

  2. Named-table (and therefore column-level) grants require the table to EXIST in the catalog,
     which only happens after the crawler's first run. Before that, the strongest valid grant is
     a table *wildcard* on the database. So this stack is two-phase by design:
       - pre-crawl  (curated_table_name=None): grant SELECT on ALL tables (wildcard).
       - post-crawl (curated_table_name="<table>"): grant column-level SELECT that EXCLUDES a
         sensitive column, demonstrating the fine-grained masking that justifies Lake Formation.

Tier 3 (AGENTS.md): governance/permission changes carry blast-radius risk -> human review.
"""
from typing import Optional

from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lakeformation as lakeformation,
)
from constructs import Construct

# Column the analyst persona is NOT allowed to see, to make column-level masking concrete.
# (Curated schema: id, event_time, amount, category -- see src/glue/curated_etl.py.)
_SENSITIVE_COLUMN = "amount"


class GovernanceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        curated_bucket: s3.IBucket,
        database_name: str,
        curated_table_name: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.curated_bucket = curated_bucket
        self.database_name = database_name

        # 1. Register the curated S3 location with Lake Formation so LF -- not just IAM -- governs
        #    access to objects under it. use_service_linked_role=True lets LF create/use
        #    AWSServiceRoleForLakeFormationDataAccess to read the data on a grantee's behalf, so
        #    Athena queries succeed without handing analysts direct s3:GetObject on the bucket.
        curated_location = lakeformation.CfnResource(
            self,
            "CuratedLocation",
            resource_arn=curated_bucket.bucket_arn,
            use_service_linked_role=True,
        )

        # 2. The analyst persona: a role that gets ONLY Lake Formation grants, no S3/Glue policies.
        #    That's the whole point -- LF, not an IAM policy, decides what data it can read. In a
        #    real deployment this would be assumed via SSO/federation; here it's a bare role so the
        #    grant wiring is the thing on display.
        self.analyst_role = iam.Role(
            self,
            "AnalystRole",
            role_name="dea-c01-analyst",
            assumed_by=iam.AccountRootPrincipal(),  # study project: assumable within the account
            description="Least-privilege analyst; data access comes only from Lake Formation grants.",
        )
        analyst_principal = lakeformation.CfnPermissions.DataLakePrincipalProperty(
            data_lake_principal_identifier=self.analyst_role.role_arn
        )

        # 3a. DESCRIBE on the database so the analyst can see the table exists in the catalog.
        #     (Without this, even a valid SELECT grant leaves the table invisible in Athena.)
        db_describe = lakeformation.CfnPermissions(
            self,
            "AnalystDescribeDatabase",
            data_lake_principal=analyst_principal,
            resource=lakeformation.CfnPermissions.ResourceProperty(
                database_resource=lakeformation.CfnPermissions.DatabaseResourceProperty(
                    catalog_id=self.account,
                    name=database_name,
                )
            ),
            permissions=["DESCRIBE"],
        )

        # 3b. SELECT on the data. Two-phase (see module docstring):
        if curated_table_name is None:
            # Pre-crawl: no named table exists yet, so grant SELECT on ALL tables (wildcard).
            # Coarse but valid -- the strongest grant possible before the catalog is populated.
            table_resource = lakeformation.CfnPermissions.TableResourceProperty(
                catalog_id=self.account,
                database_name=database_name,
                table_wildcard={},  # {} == "every table in this database"
            )
            select_grant = lakeformation.CfnPermissions(
                self,
                "AnalystSelectAllTables",
                data_lake_principal=analyst_principal,
                resource=lakeformation.CfnPermissions.ResourceProperty(
                    table_resource=table_resource
                ),
                permissions=["SELECT"],
            )
        else:
            # Post-crawl: the fine-grained showcase. Grant SELECT on the named table but EXCLUDE
            # the sensitive column -- Athena will transparently hide `amount` from this analyst.
            # This column-level masking is what a bucket policy fundamentally cannot do.
            select_grant = lakeformation.CfnPermissions(
                self,
                "AnalystSelectMaskedColumns",
                data_lake_principal=analyst_principal,
                resource=lakeformation.CfnPermissions.ResourceProperty(
                    table_with_columns_resource=(
                        lakeformation.CfnPermissions.TableWithColumnsResourceProperty(
                            catalog_id=self.account,
                            database_name=database_name,
                            name=curated_table_name,
                            # column_wildcard + excluded == "all columns EXCEPT these".
                            column_wildcard=lakeformation.CfnPermissions.ColumnWildcardProperty(
                                excluded_column_names=[_SENSITIVE_COLUMN]
                            ),
                        )
                    )
                ),
                permissions=["SELECT"],
            )

        # A grant references the S3 location by ARN; if LF hasn't registered it yet, the grant
        # can race ahead and fail. Pin the ordering explicitly (CloudFormation can't infer it
        # from a string database_name, so we make the data dependency a real one).
        db_describe.add_dependency(curated_location)
        select_grant.add_dependency(curated_location)
