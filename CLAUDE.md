# CLAUDE.md — Serverless Lakehouse (DEA-C01 study project)

> Companion to `AGENTS.md`. **AGENTS.md = how an agent may act. This file = what the code is.**
> Keep volatile facts (bucket names, schemas) re-read from the current branch, not memory.

## What this is

A serverless batch + micro-streaming **lakehouse** on AWS, built to practice for the
**AWS Certified Data Engineer – Associate (DEA-C01)** exam on a **~$20–30 total budget**.
Everything is serverless / pay-per-use and deployed via **AWS CDK (Python)** so it can be
destroyed with one command.

## Architecture

```
 generator Lambda ─► Kinesis Firehose ─► S3 raw/ ─► Glue Crawler ─► Glue Data Catalog
                                                          │
        EventBridge ─► Step Functions ─► Glue ETL (PySpark) ─► S3 curated/ (partitioned Parquet)
                                          + Glue Data Quality        │
                                                       Lake Formation (fine-grained) ─► Athena ─► QuickSight
```

| Layer | Service | Code |
|---|---|---|
| Ingest | Kinesis Firehose, generator Lambda | `src/lambda/generator/` |
| Raw/curated storage | S3 (KMS-encrypted, lifecycle) | `iac/stacks/storage_stack.py` |
| Catalog + ETL | Glue DB, Crawler, PySpark job, Data Quality | `iac/stacks/catalog_glue_stack.py`, `src/glue/` |
| Orchestration | Step Functions + EventBridge | `iac/stacks/orchestration_stack.py` |
| Governance | Lake Formation, KMS, IAM | `iac/stacks/governance_stack.py` |
| Query | Athena (exploratory SQL) | `analysis/` |

## Commands

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
cdk synth                      # render CloudFormation, no deploy
cdk deploy --all               # deploy (uses your AWS CLI profile / region)
cdk destroy --all              # TEAR DOWN — run after every session
pytest                         # unit tests (Glue transform + helpers)
```

## Cost guardrails — READ BEFORE DEPLOYING

- **Tear down after every session:** `cdk destroy --all`. Kinesis/Firehose and any stream bill
  while running.
- Keep sample data in **MB, not GB** — Athena/Glue cost scales with bytes scanned/processed.
- Set an **AWS Budgets** alert at $10 and $20 and a CloudWatch billing alarm before first deploy.
- All resources are tagged `project=dea-c01` — check spend in Cost Explorer by that tag.
- Prefer `dea-c01-*` resource names so the deploy IAM role can be scoped to them (least privilege).

## Conventions

- **Conventional Commit scopes:** `iac`, `glue`, `lambda`, `catalog`, `lakeformation`, `athena`, `ci`.
- Partition curated data by `year/month/day`; write **Parquet**, not CSV/JSON, to the curated zone.
- Parameterize all SQL; never string-build queries from input.
- Tier of every path is defined in `AGENTS.md §1` and enforced via `.github/CODEOWNERS`.

## What's a skeleton (flesh these out)

- `src/glue/curated_etl.py` — transform body + Data Quality ruleset are TODO stubs.
- `iac/stacks/governance_stack.py` — Lake Formation grants are documented placeholders.
- `src/lambda/generator/handler.py` — emits sample records; swap in your real dataset.
