## Summary

<!-- What and why -->

## Change type

- [ ] feat
- [ ] fix
- [ ] refactor
- [ ] chore / docs / test / ci

## Highest tier touched (AGENTS.md §1)

- [ ] Tier 1 — autonomous
- [ ] Tier 2 — CI-gated
- [ ] Tier 3 — human review required (CODEOWNERS)

## DEA-C01 domain(s) advanced

<!-- e.g. D1 ingestion, D4 security — see docs/EXAM_ALIGNMENT.md -->

## Test plan

<!-- cdk synth output / pytest / manual Athena query -->

## Confirmations

- [ ] No secrets, keys, or real `.env` added to any tracked file.
- [ ] If infra changed: `cdk synth` succeeds and resources stay tagged `project=dea-c01`.
- [ ] If this touches a Tier 3 path, a human will review before merge.
