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

LF and IAM are BOTH required, and they answer different questions (internalize this for D4):
  - IAM  -> "may this principal *call* Athena/Glue APIs and use the KMS key?"
  - LF   -> "which databases / tables / *columns* may it read?"
  A query succeeds only when both say yes. So this stack does two things that look redundant but
  aren't: it issues LF grants (the data layer) AND gives the analyst baseline IAM (the API layer).

------------------------------------------------------------------------------------------------
OPERATOR RUNBOOK -- manual steps CDK cannot safely automate (do these once, per account+region):

  [M1] Designate the deploy identity as a Lake Formation data-lake ADMIN.
       WHEN: once, BEFORE the first `cdk deploy` of this stack.
       HOW:  LF console -> Administrative roles and tasks -> Data lake administrators -> Add
             (add the OIDC deploy role ARN from .github/workflows/deploy.yml, and yourself).
       WHY not in code: writing CfnDataLakeSettings.admins REPLACES the whole admin list rather
             than appending -- a wrong value locks everyone (incl. this deploy role) out of LF.

  [M2] Turn OFF the "Use only IAM access control" defaults for new databases and tables.
       WHEN: once, BEFORE the crawler first runs.
       HOW:  LF console -> Data Catalog settings -> uncheck BOTH default-permission checkboxes.
       WHY:  otherwise LF auto-grants `Super` to the `IAMAllowedPrincipals` group on every new
             table, which makes the table fall back to pure-IAM control and SILENTLY bypasses
             the column masking below. Nothing errors -- the analyst just sees `amount` anyway.

  [M3] After the crawler creates the curated table, REVOKE `Super` from `IAMAllowedPrincipals`
       on the database and the table, then redeploy this stack with `curated_table_name` set.
       WHEN: after the first crawl, before you rely on masking.
       HOW:  LF console -> Databases/Tables -> View permissions -> revoke IAMAllowedPrincipals.

  Deploy-role scope (IAM, one-time): the deploy role also needs `lakeformation:RegisterResource`,
  `lakeformation:GrantPermissions`, and `iam:PassRole` for the registration role created below.
------------------------------------------------------------------------------------------------

Tier 3 (AGENTS.md): governance/permission changes carry blast-radius risk -> human review.
"""
from typing import Optional

from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_kms as kms,
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
        data_key: kms.IKey,
        athena_results_bucket: s3.IBucket,
        database_name: str,
        glue_role_arn: str,
        curated_table_name: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.curated_bucket = curated_bucket
        self.database_name = database_name

        # ---- Registration role: how LF reads the KMS-ENCRYPTED curated data on a grantee's behalf.
        # We register the location with a CUSTOM role instead of use_service_linked_role=True on
        # purpose. The service-linked role would need permissions on the customer-managed KMS key,
        # but adding a not-yet-existent SLR to a KMS key policy fails KMS's principal-existence
        # check -> a deploy-order trap. An explicit role we create and grant is deployable in one
        # pass and shows the "registration role" concept the exam expects. LF assumes this role
        # (trust: lakeformation.amazonaws.com) to vend scoped credentials to Athena/Glue at query
        # time -- which is why analysts never need direct s3:GetObject on the curated bucket.
        registration_role = iam.Role(
            self,
            "LakeFormationDataAccessRole",
            role_name="dea-c01-lf-data-access",
            assumed_by=iam.ServicePrincipal("lakeformation.amazonaws.com"),
            description="LF assumes this to read the KMS-encrypted curated zone for grantees.",
        )
        curated_bucket.grant_read(registration_role)
        data_key.grant_decrypt(registration_role)  # required: curated objects are CMK-encrypted

        # 1. Register the curated S3 location with Lake Formation so LF -- not just IAM -- governs
        #    access to objects under it, using the role above to reach the encrypted data.
        curated_location = lakeformation.CfnResource(
            self,
            "CuratedLocation",
            resource_arn=curated_bucket.bucket_arn,
            use_service_linked_role=False,  # we register with our own role instead (above)
            role_arn=registration_role.role_arn,
        )

        # Once a location is LF-registered, creating a catalog table that POINTS at it requires the
        # creating principal to hold DATA_LOCATION_ACCESS on that location -- a separate permission
        # from the database CREATE_TABLE grant in catalog_glue_stack.py. Grant it to the Glue role
        # so the curated crawler can register its table over the curated zone. (The analyst does NOT
        # need this: DATA_LOCATION_ACCESS gates *writing metadata* on a location, not SELECT.)
        glue_location_access = lakeformation.CfnPermissions(
            self,
            "GlueCuratedLocationAccess",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=glue_role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                data_location_resource=lakeformation.CfnPermissions.DataLocationResourceProperty(
                    catalog_id=self.account,
                    s3_resource=curated_bucket.bucket_arn,
                )
            ),
            permissions=["DATA_LOCATION_ACCESS"],
        )
        glue_location_access.add_dependency(curated_location)

        # 2. The analyst persona. Its DATA access comes only from LF grants (below), but LF governs
        #    data, not API calls -- so it still needs baseline IAM to *run a query at all*:
        #      - athena:*  to submit/read queries
        #      - glue:Get* to resolve the catalog table (LF DESCRIBE gates the rows this returns)
        #      - lakeformation:GetDataAccess  so Athena can fetch LF-vended credentials
        #      - read/write on the Athena RESULTS bucket + its KMS key (results are CMK-encrypted)
        #    Note: it deliberately has NO curated-bucket S3 access -- LF is the only path to that
        #    data, which is the whole point.
        self.analyst_role = iam.Role(
            self,
            "AnalystRole",
            role_name="dea-c01-analyst",
            assumed_by=iam.AccountRootPrincipal(),  # study project: assumable within the account
            description="Least-privilege analyst; curated data access comes only from LF grants.",
        )
        self.analyst_role.add_to_policy(
            iam.PolicyStatement(
                sid="AthenaQuery",
                actions=[
                    "athena:StartQueryExecution",
                    "athena:StopQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:GetWorkGroup",
                ],
                resources=["*"],
            )
        )
        self.analyst_role.add_to_policy(
            iam.PolicyStatement(
                sid="CatalogRead",
                actions=[
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                ],
                resources=["*"],
            )
        )
        self.analyst_role.add_to_policy(
            iam.PolicyStatement(
                # Athena calls this to exchange the LF grant for temporary data credentials.
                sid="LakeFormationCredentialVending",
                actions=["lakeformation:GetDataAccess"],
                resources=["*"],
            )
        )
        # Athena writes query output to the results bucket (CMK-encrypted), then reads it back.
        athena_results_bucket.grant_read_write(self.analyst_role)
        data_key.grant_encrypt_decrypt(self.analyst_role)  # for those encrypted results only

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

        # 3b. SELECT on the data. Two-phase (see the runbook: named grants need the table to exist):
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
            # This column-level masking is what a bucket policy fundamentally cannot do. (Only
            # takes effect once IAMAllowedPrincipals has been removed from the table -- see [M3].)
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
