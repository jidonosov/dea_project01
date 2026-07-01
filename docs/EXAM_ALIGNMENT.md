# Exam alignment — governance practices ↔ DEA-C01 domains

Following `AGENTS.md` is not just hygiene: several governance requirements are themselves
DEA-C01 exam objectives. This is the map.

| Governance practice (AGENTS.md) | DEA-C01 domain | What you learn |
|---|---|---|
| OIDC deploy, no long-lived keys (§4) | **D4** Security & Governance | STS temporary credentials, scoped IAM trust policies |
| Least-privilege deploy role scoped to `dea-c01-*` (§4) | **D4** | IAM least privilege over `*` |
| Secret scanning, Secrets Manager / SSM, no creds in git (§5) | **D4** | Credential management services |
| `checkov`/`cfn-nag` enforcing encryption + access (§4) | **D4** | Encryption at rest/in transit, public-access controls |
| Additive-only schema changes (§1 Tier 2) | **D2** Data Store Mgmt | Schema evolution in the Glue Catalog |
| CloudTrail + CloudWatch baked into stacks, monitored | **D3** Operations | Monitoring, logging, auditing |
| IaC reproducible build + one-command teardown (§4) | **D3** | Automation, cost optimization |
| Glue Data Quality rules in the ETL (T3 review) | **D1 / D3** | Data validation, quality gating |

## DEA-C01 domain weighting (reference)

| Domain | Weight |
|---|---|
| D1 Data Ingestion & Transformation | 34% |
| D2 Data Store Management | 26% |
| D3 Data Operations & Support | 22% |
| D4 Data Security & Governance | 18% |

> Note: `AGENTS.md §6` (agentic-AI / Claude Architect domains) does **not** apply to this
> pipeline — there is no LLM in the product. It constrains only how Claude Code helps build it.

## Convention: capture the "why over the alternative", not just the fact

DEA-C01 mostly tests choosing the best-fit service among competing valid options under given
constraints — not isolated facts. So each row added here (and each stack/module docstring, per
`CLAUDE.md`) should be able to answer, in one line: *what else could have done this job, and why
was it rejected here?* Examples already implicit in this repo's design:

| Decision made here | Plausible alternative | Why rejected in this context |
|---|---|---|
| Kinesis Firehose for ingest | Kinesis Data Streams + Lambda consumer | Firehose needs no consumer code/scaling logic for a simple land-to-S3 path; Data Streams only earns its complexity at higher throughput or when multiple consumers need the same stream |
| Glue (Spark) ETL | EMR | Glue is serverless/pay-per-job; EMR's cluster-uptime billing and ops overhead only pay off at a scale/customization this study project doesn't have |
| Step Functions + EventBridge | Managed Workflows for Apache Airflow (MWAA) | MWAA bills for the environment 24/7 whether it's orchestrating or idle; Step Functions is pay-per-transition and fits a small serverless budget |
| Athena for exploratory SQL | Redshift Serverless as primary query layer | Athena queries S3 directly with no warehouse to provision/pause; Redshift Serverless is exercised separately as one of the mini-projects, not the main pipeline's query layer |

Keep adding rows like this as skeleton files get fleshed out (e.g. once `curated_etl.py`'s Data
Quality ruleset is real, note why Glue Data Quality was chosen over Deequ-on-EMR or a custom
pytest-based check).
