# AWS Serverless Lakehouse — DEA-C01 Study Project

A serverless batch + streaming lakehouse (S3 · Glue · Athena · Kinesis Firehose · Step Functions ·
Lake Formation) built to practice for the **AWS Certified Data Engineer – Associate** exam on a
**~$20–30 budget**. Infrastructure is **AWS CDK (Python)**; one command tears it all down.

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cdk synth                 # validate, no AWS calls beyond credentials
cdk deploy --all          # deploy to the account in your AWS CLI profile
# ... work, query in Athena ...
cdk destroy --all         # ALWAYS tear down when done (cost control)
```

## How it works — Infrastructure as Code

You define all AWS resources (S3, Glue, IAM, Step Functions, KMS) **in the CDK Python files** —
you do **not** build them by hand in the AWS console. CDK translates your Python in two steps:

```
iac/stacks/*.py  --cdk synth-->  CloudFormation template  --cdk deploy-->  real AWS resources
```

- `cdk synth` — renders the template locally; no resources created (CI runs this on every PR).
- `cdk deploy --all` — CloudFormation provisions everything in dependency order, one command.
- `cdk destroy --all` — deletes it all just as cleanly (this is what keeps the project on-budget).

The console becomes a place to **query and inspect** results (Athena, S3, CloudWatch), not to
build infrastructure.

### One-time setup (per account/region)

```bash
cdk bootstrap            # creates a small support stack (assets bucket + deploy roles). Run once.
```

The only other manual step is designating a **Lake Formation data-lake admin** in the console
before fine-grained grants work (see `iac/stacks/governance_stack.py`). Everything else is code.

> DEA-C01: this is **Domain 3** (deployment automation). CDK *synthesizes to CloudFormation* —
> it does not call AWS APIs directly. Infrastructure *definitions* live in code; *runtime state*
> (crawler-inferred schemas, written partitions, query results) appears at deploy/run time.

## Repo layout

| Path | What | Tier (see `AGENTS.md`) |
|---|---|---|
| `iac/` | CDK stacks (storage, catalog+glue, orchestration, governance) | T3 |
| `src/glue/` | PySpark ETL + Glue Data Quality rules | T3 |
| `src/lambda/` | Data generator / consumers | T2 (with tests) |
| `src/common/` | Pure-logic helpers | T2 |
| `analysis/` | Exploratory Athena SQL | T1 |
| `tests/` | pytest | T1 |
| `.github/` | CI/CD, CODEOWNERS, templates | T3 |
| `.claude/` | Claude Code settings + hooks | T3 |

## Governance

This repo follows the AI development governance playbook in **[`AGENTS.md`](AGENTS.md)**:
autonomy tiers, PR-only workflow, CI gating, OIDC deploys (no long-lived keys). See
**[`docs/EXAM_ALIGNMENT.md`](docs/EXAM_ALIGNMENT.md)** for how the governance practices map onto
DEA-C01 exam domains.

> ⚠️ This is a learning scaffold. Several files are intentional stubs — see "What's a skeleton" in
> [`CLAUDE.md`](CLAUDE.md).
