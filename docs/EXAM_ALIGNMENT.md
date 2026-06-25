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
