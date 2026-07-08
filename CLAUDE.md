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

## Educational intent — this is a study artifact, not just working infra

This repo's primary purpose is to **teach DEA-C01**, not to ship a product. The DEA-C01 exam
mostly tests judgment between competing valid AWS services/patterns (e.g. Firehose vs. Kinesis
Data Streams, Glue vs. EMR, Step Functions vs. MWAA, Athena vs. Redshift Spectrum) under given
constraints (cost, latency, ops overhead, scale) — not rote service facts. So documentation here
must carry that reasoning, not just describe what the code does:

- **Every stack/module docstring** states: (1) what it is, (2) the DEA-C01 domain(s) it maps to
  (see `docs/EXAM_ALIGNMENT.md`), and (3) **why this service/pattern was chosen over the
  plausible alternative(s)** in this project's specific context — see the header of
  `iac/stacks/storage_stack.py` for the domain-tagging style; extend it with the "why over X"
  reasoning when adding or fleshing out a stack.
- **Inline comments** explain non-obvious AWS behavior, limits, or cost drivers a reader would
  otherwise only learn by getting burned in production (e.g. why `RemovalPolicy.DESTROY` is used
  here vs. `RETAIN` in a real deployment, why worker counts are pinned to the minimum).
- When fleshing out a skeleton (see "What's a skeleton" below), don't just make it work — make it
  teach. Add the trade-off reasoning as you replace a TODO with real logic.
- When a change introduces new exam-relevant reasoning, add a row to `docs/EXAM_ALIGNMENT.md`
  so the domain map stays current with the code.

## Conventions

- **Conventional Commit scopes:** `iac`, `glue`, `lambda`, `catalog`, `lakeformation`, `athena`, `ci`.
- Partition curated data by `year/month/day`; write **Parquet**, not CSV/JSON, to the curated zone.
- Parameterize all SQL; never string-build queries from input.
- Tier of every path is defined in `AGENTS.md §1` and enforced via `.github/CODEOWNERS`.

## What's a skeleton (flesh these out)

_None — the pipeline is fully fleshed out. Map of what's real below._

Fleshed out (kept here as a map of what's real):
- `src/lambda/generator/handler.py` — realistic-synthetic **e-commerce order** generator. Always
  injects at-least-once duplicates + null keys (transform cleans them); opt-in `INJECT_DQ_VIOLATIONS`
  (env or event) plants rows that fail the Data Quality gate to demo it blocking a bad load.
- `src/glue/curated_etl.py` — transform + Data Quality ruleset are implemented (enriched schema:
  `order_id`, `event_time`, `customer_id`, `category`, `quantity`, `unit_price`, `amount`, …).
- `iac/stacks/catalog_glue_stack.py` — raw **and** curated crawlers + the Glue role's Lake
  Formation grants (needed once the IAM-only default is off).
- `iac/stacks/governance_stack.py` — Lake Formation location registration + analyst grants are
  implemented (pre-crawl table-wildcard SELECT; post-crawl column-masked SELECT). Deploy still
  needs a Lake Formation data-lake admin designated once (see the stack docstring / README).
