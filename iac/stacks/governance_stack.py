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

  [M1] Designate the CDK CLOUDFORMATION EXECUTION ROLE as a Lake Formation data-lake ADMIN
       (and your own admin identity, for console work).
       WHEN: once, BEFORE the first `cdk deploy` of this stack.
       HOW:  LF console -> Administrative roles and tasks -> Data lake administrators -> Add
             both `cdk-hnb659fds-cfn-exec-role-<acct>-<region>` and your admin user/role.
       WHY the exec role specifically: `cdk deploy` does NOT call CloudFormation as your CLI
             identity -- it assumes the bootstrap execution role, and THAT role is what issues the
             LF grants in this stack. If it isn't an LF admin, grants on resources it didn't create
             (e.g. DATA_LOCATION_ACCESS on an out-of-band-registered location, or SELECT on a
             crawler-made table) fail with "requester is not authorized". Database grants happen to
             work without it only because the exec role creates the database and thus owns it.
       WHY not in code: writing CfnDataLakeSettings.admins REPLACES the whole admin list rather
             than appending -- a wrong value locks everyone (incl. this deploy role) out of LF.

  [M2] Turn OFF the "Use only IAM access control" defaults for new databases and tables.
       WHEN: once, BEFORE the crawler first runs.
       HOW:  LF console -> Data Catalog settings -> uncheck BOTH default-permission checkboxes.
       WHY:  otherwise LF auto-grants `Super` to the `IAMAllowedPrincipals` group on every new
             table, which makes the table fall back to pure-IAM control and SILENTLY bypasses
             the column masking below. Nothing errors -- the analyst just sees `amount` anyway.

  [M-reg] Register the curated S3 location with Lake Formation, using the service-linked role,
       and grant that SLR kms:Decrypt on the curated CMK so it can read the encrypted data.
       WHEN: once, AFTER storage is deployed (bucket + key exist), BEFORE deploying this stack.
       HOW:  aws lakeformation register-resource --resource-arn arn:aws:s3:::<curated-bucket> \
                 --use-service-linked-role
             aws kms create-grant --key-id <curated-cmk> \
                 --grantee-principal arn:aws:iam::<acct>:role/aws-service-role/\
lakeformation.amazonaws.com/AWSServiceRoleForLakeFormationDataAccess \
                 --operations Decrypt
       WHY not in code: (1) a CfnResource registration and the DATA_LOCATION_ACCESS grant below
             race -- LF needs seconds to propagate a new registration and CFN can't wait between
             resources; (2) granting the SLR KMS from this stack would make the storage stack
             (owner of the key) depend on this one -> a cross-stack cycle. Out of band avoids both.

  [M3] After the crawler creates the curated table, REVOKE `Super` from `IAMAllowedPrincipals`
       on the database and the table, then redeploy this stack with `curated_table_name` set.
       WHEN: after the first crawl, before you rely on masking.
       HOW:  LF console -> Databases/Tables -> View permissions -> revoke IAMAllowedPrincipals.

  Deploy-role scope (IAM, one-time): the deploy role also needs `lakeformation:GrantPermissions`
  (to issue the grants below). Registration itself is [M-reg], done out of band.
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
# `amount` is the order total (revenue) -- a believable "analysts see orders, not revenue" case.
# (Curated schema: order_id, event_time, customer_id, category, quantity, unit_price, amount, ...
#  -- see src/glue/curated_etl.py.)
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

        # ---- Location registration is done OUT OF BAND (runbook [M-reg]), NOT here. Two reasons:
        #  1. Register -> grant race: CloudFormation fires the DATA_LOCATION_ACCESS grant below
        #     within ~1s of a CfnResource registration completing, but Lake Formation needs a few
        #     seconds to propagate a new registration -> the grant intermittently fails with a
        #     spurious AccessDenied. There is no CFN-native way to wait between the two.
        #  2. Registering with the LF service-linked role (which then reads the KMS-encrypted
        #     curated data for grantees) means the SLR needs kms:Decrypt on the curated CMK. Adding
        #     that to the key policy from THIS stack would make the storage stack (which owns the
        #     key) depend on this one -> a cross-stack cycle. Doing it out of band avoids both.
        # So [M-reg] (see docstring) registers the curated bucket with the SLR and grants the SLR
        # kms:Decrypt via a KMS grant. Everything below just references the already-registered
        # location, so no race and no cycle.

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

        # 3b. SELECT on the data. Two-phase (named grants need the table to exist -- see runbook):
        #   - pre-crawl (curated_table_name=None): NO table grant. The analyst can see the database
        #     (DESCRIBE above) but there is no curated table yet, so there is nothing to read. We
        #     deliberately do NOT grant a table-WILDCARD SELECT here: it would be broader than least
        #     privilege, and the legacy AWS::LakeFormation::Permissions CloudFormation resource
        #     fails on `TableWildcard` with a spurious AccessDenied (a CFN-resource defect -- the
        #     GrantPermissions API accepts the same grant). The masked grant below is the showcase.
        #   - post-crawl (curated_table_name set): column-masked SELECT on the named curated table.
        select_grant = None
        if curated_table_name is not None:
            # The fine-grained showcase. Grant SELECT on the named table but EXCLUDE the sensitive
            # column -- Athena transparently hides `amount` from this analyst. This column-level
            # masking is what a bucket policy fundamentally cannot do. (Only takes effect once
            # IAMAllowedPrincipals has been removed from the table -- see [M3].) A named table +
            # ColumnWildcard works with the legacy CFN resource; only *table* wildcards are broken.
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

        # Chain the grants so only one LF permission op is in flight at a time (LF's permission
        # API is not reliably concurrent -- parallel grants can spuriously fail).
        db_describe.add_dependency(glue_location_access)
        if select_grant is not None:
            select_grant.add_dependency(db_describe)
