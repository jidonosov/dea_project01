# AI Development Governance — Portable Playbook

> **What this file is.** A **project-agnostic** governance template for using AI coding
> agents (Claude Code first, but written to apply to any agent — Copilot, Cursor, etc.) across
> the full software development lifecycle. It defines *how an agent is allowed to act*, how
> work flows through git/GitHub/CI-CD, and the engineering standards every AI-assisted change
> must meet — including the **agentic-AI good practices** drawn from the Claude Certified
> Architect domains.
>
> **How to use it.** Drop this file into a new repository and rename it `AGENTS.md` at the repo
> root (the emerging cross-tool standard filename). Then do the **Adoption checklist** at the
> bottom: fill in the tier table with *your* repo's files, wire the hook + CI, and add a
> `CLAUDE.md` for project-specific context. Keep this file describing *how an agent may act*;
> keep `CLAUDE.md` describing *what the code is*.
>
> Anything in `<angle brackets>` or a **PROJECT:** note is a placeholder to replace per repo.
>
> **Tool stance — Claude-first (decided).** This playbook is written **Claude-first on
> purpose**: it assumes Claude Code as the primary agent and keeps the `.claude/` configuration
> kit (§7) inline rather than in a tool-neutral appendix. The *governance* (autonomy tiers,
> SDLC, git/GitHub enforcement, CI/CD, security, and the agentic-AI standards in §6) is
> tool-agnostic and applies to any agent — only the **mechanics** in §7 (`settings.json`,
> commands, skills, subagents, hooks) are Claude-specific. Teams using Copilot, Cursor, or
> another agent should keep §0–§6 and §8–§9 as-is and translate §7 to their tool's equivalent
> (e.g. its own config, hook, and reviewer mechanisms). This is a deliberate choice, not an
> oversight; revisit it only if the primary agent changes.

---

## 0. Document model — separation of concerns

Use a small, explicit hierarchy so each instruction has exactly one home. Agents read all of
them; humans maintain them deliberately.

| File | Answers | Audience |
|---|---|---|
| `AGENTS.md` (this file, renamed) | *How may an agent act?* Autonomy, SDLC, guardrails | Any AI agent |
| `CLAUDE.md` | *What is this code?* Architecture, conventions, pitfalls, commands | Claude Code |
| `CLAUDE.local.md` (git-ignored) | Personal/local notes, local DB hosts, machine quirks | The individual dev |
| `.claude/settings.json` | Permissions + hooks (the harness enforces these, not the model) | Claude Code |
| `README.md` | Human onboarding | People |
| `docs/` | Deep-dives (CI, deploy, design decisions, this playbook) | People + agents |

**Nested context files are encouraged.** A large repo can carry a `CLAUDE.md` per major
subsystem (e.g. `etl/CLAUDE.md`, `serverless/CLAUDE.md`) so an agent working in that directory
gets local context without loading the whole tree. This is the "CLAUDE.md hierarchy" pattern.

**Golden rule of self-modification:** an agent must never weaken its own guardrails. Files that
define permissions, autonomy, CI, or review policy are always human-review-only (see Tier 3).

---

## 1. Autonomy tiers — the core model

> **Principle:** preserve delivery velocity by requiring human approval only where it
> *materially* reduces risk. Do not add approval gates that create friction without reducing
> harm. A file's tier is set by **irreversibility, security exposure, and the risk of silent
> data/quality corruption** — not by how "important" it feels.

### Tier 1 — Fully autonomous (no CI gate, no human gate)

An agent may do these without asking:

- Read, search, and analyze any file in the repo.
- Create, switch, rename, and delete **feature** branches.
- Add or edit tests.
- Add or edit ad-hoc diagnostic scripts that are **not** part of the shipped app.
- Edit `README.md`, `CHANGELOG.md`, `docs/`, and any `.md` not listed in CODEOWNERS.
- Add or remove inline code comments.
- Create GitHub Issues; open pull requests (opening a PR ≠ merging it); push additional
  commits to an already-open PR branch.

### Tier 2 — CI-gated (machine-reviewed, no human gate required)

An agent may change these on a feature branch **if all CI checks pass**. These files have
behavior covered by the test suite, so a regression surfaces in CI. Human review is welcome but
not required to merge.

- **PROJECT:** application entry points / wiring whose behavior is exercised by tests.
- Pure-logic modules with good test coverage.
- **Additive-only** schema changes (adding a new column/field — never renaming/removing).
- Single-line version/changelog bumps.

**Gate condition:** the CI workflow (tests + lint + security scan + secret scan) must be green.
A failing CI blocks the merge regardless of anything else. **When CI fails, the agent may push
fixes to the same branch autonomously until it passes** — no human needed for CI fixes.

### Tier 3 — Human approval required (CI **and** CODEOWNERS review)

These carry irreversibility risk, security exposure, or can silently corrupt data quality.
Both CI **and** an explicit human review (enforced by CODEOWNERS) are required before merge.

| Category | Why human review |
|---|---|
| Auto-generated files | Hand edits are silently lost on regenerate — fix the source instead |
| DB access / credential resolution | Security-critical |
| Single source-of-truth state modules | Every component depends on them |
| Data-transform / mapping / validation logic | Silent data-quality corruption risk |
| Dependency manifests (`requirements.txt`, `package.json`, lockfiles) | Supply-chain risk |
| Build / packaging / IaC / cloud handlers | Irreversibility + secrets exposure |
| **Agent governance itself** — this file, `CLAUDE.md`, hooks, `settings.json`, CI workflows, CODEOWNERS | Self-modification is a conflict of interest |
| Any credential-bearing file (`.env`, keys) | Must never be committed |

CODEOWNERS enforces Tier 3 at the platform level: a PR touching any listed path cannot be
merged without the named reviewer's approval, *regardless of CI status*.

> **PROJECT:** Replace the categories above with the actual file paths in your repo, then mirror
> them into `.github/CODEOWNERS`. The tier table is the contract; CODEOWNERS is the enforcement.

---

## 2. SDLC workflow

```
1. Task defined in a GitHub Issue or PR comment — tag any Architect domain(s) it advances (§6)
2. Agent creates a branch: feat/* | fix/* | chore/* | refactor/* | docs/*
3. Agent edits files on the branch
4. Agent commits using Conventional Commits: type(scope): message
5. Agent opens a PR — NEVER pushes directly to main
6. CI runs automatically
7. If CI fails: agent pushes fixes to the same branch (no human needed)
8. If the PR touches Tier 3 files: a human reviews the diff on GitHub
9. A human merges — the agent never self-approves or self-merges
```

**Branching**
- One branch per task; branch off `main`. Never commit to `main` directly.
- Naming: `<type>/<short-kebab-slug>` (≤ ~40 chars), e.g. `feat/heatmap-time-filter`.

**Commits — [Conventional Commits](https://www.conventionalcommits.org/)**
- Format: `type(scope): subject` — `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`, `ci`.
- **PROJECT:** define your scope vocabulary (e.g. `api`, `ui`, `db`, `etl`, `build`, `ci`).
- `feat` → MINOR, `fix` → PATCH, `feat!`/`BREAKING CHANGE:` → MAJOR (SemVer).
- Keep the subject imperative and ≤ ~70 chars; put the *why* in the body.
- **Do not suggest or create commits unless explicitly asked** (a common standing preference —
  keep it unless your project says otherwise).

**Pull requests**
- Open against `main`; never close-and-reopen to "refresh" — push to the same branch and the PR
  updates automatically.
- Use a PR template that forces: summary, change type, **tier touched**, **Architect domain(s)
  touched**, test plan, and a secrets/no-`.env` confirmation.
- The PR author (human or agent) states the highest tier touched so reviewers know the bar.

**Changelog & versioning**
- Follow [Keep a Changelog](https://keepachangelog.com/) + SemVer. Derive entries from
  Conventional Commit types.

---

## 3. Git & GitHub configuration (the enforcement layer)

Instructions in markdown are advisory. **Real guardrails are enforced by the platform and
hooks**, so an agent cannot talk its way past them.

**Branch protection on `main`** (repo settings):
- Require a PR before merging; require status checks to pass; require CODEOWNERS review on
  protected paths; disallow force-push and direct push.

**CODEOWNERS** — maps every Tier 3 path to a required reviewer. This is what makes "human
approval required" actually true.

**Local hook (defense in depth)** — a `PreToolUse` hook blocks the agent from ever running a
direct `git push` to `main`/`master`, so the violation is caught *before* it reaches the
platform. Example (deny push to the protected branch, defer everything else):

```bash
# .claude/hooks/pre-tool-use.sh  — wired via .claude/settings.json "hooks" key
INPUT=$(cat)
if printf '%s' "$INPUT" \
  | grep -qE 'git[[:space:]]+push[^"]*[^"A-Za-z0-9_/.-](main|master)[[:space:]]*"'; then
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Direct push to main is blocked. Branch + open a PR."}}'
    exit 0
fi
exit 0   # no match → defer to the normal permission flow
```

**Issue & PR templates** — see `.github/ISSUE_TEMPLATE/` and `PULL_REQUEST_TEMPLATE.md`. An
"Agent Task" issue template that captures *objective / inputs / success criteria / out-of-scope
/ permitted autonomy level* turns vague asks into bounded, reviewable tasks.

**Dependabot** — weekly dependency + GitHub-Action-SHA bumps, opened as PRs that go through the
same Tier 3 review (supply-chain changes are never auto-merged).

---

## 4. CI/CD standards

CI is the machine reviewer that makes Tier 2 autonomy safe. Design it to be **fast,
least-privilege, and reproducible.**

**CI on every PR — recommended jobs:**
1. **Tests** — the full suite on a pinned runtime; headless where a GUI/display is involved.
2. **Lint / type-check** — style and static types.
3. **Security scan** — a SAST tool (e.g. Bandit for Python, `npm audit`/Semgrep, CodeQL).
4. **Secret scan** — diff-level regex for credential patterns (connection strings with inline
   passwords, cloud access keys, `BEGIN PRIVATE KEY` blocks), backstopped by the platform's
   native secret scanning.
5. **Governance consistency** — assert the agent-governance files still exist and contain their
   required sections (so a refactor can't silently delete a guardrail).
6. **Cross-product guard** (if one repo ships multiple artifacts) — cheaply compile/parse every
   product's sources so a change to one can't break another.

**Hardening rules for the workflows themselves:**
- **Least privilege:** start the workflow with `permissions: {}` and grant each job only what it
  needs (`contents: read`, etc.).
- **Pin third-party actions to a full commit SHA**, not a moving tag.
- **No long-lived cloud keys.** For deploys, use **OIDC**: the CI provider mints a short-lived
  signed token, the cloud trusts it (trust policy scoped to `repo:…:ref:refs/heads/main`) and
  returns temporary credentials that expire in minutes. Nothing to leak or rotate.
- **Scope the deploy role** to the project's own resource names (least privilege over `*`).
- **Concurrency control** so two deploys never race the same stack; consider a GitHub
  *Environment* with required reviewers as an approval gate before production.
- **Reproducible builds:** packaging/build steps run from a clean checkout; build artifacts and
  generated files are committed only where the project deliberately requires it.

**CD:** trigger on merge to `main` for the relevant paths (plus a manual dispatch). Bake
environment-specific config (API URLs, feature flags) from infra outputs / repo variables at
build time — never commit per-environment secrets.

---

## 5. Security & secrets — non-negotiable

- **Secrets live in the environment, never in git.** Use `.env` (git-ignored) locally and a
  secrets manager / parameter store / OIDC in CI and production. Never hardcode credentials,
  tokens, or keys in source, prompts, instructions, or agent memory.
- **`.gitignore` must cover** `.env`, key material, and credential files. Verify before any
  `git add .` — prefer explicit `git add <path>` over `git add .`.
- **Never echo or store secrets** found in files into memory, logs, or chat.
- **Parameterize all queries** (no string-built SQL with user/data input). Escape any
  data/user string before injecting into HTML/JS/templates.
- **Validate at the trust boundary**; fail closed with a clear error rather than silently
  proceeding on bad input.
- **Dependencies are a supply-chain surface:** new deps are Tier 3; pin and review them.

---

## 6. Agentic-AI engineering standards (Claude Certified Architect domains)

> Any feature that *uses* an LLM/agent must be built the domain-aligned way. Treat these five
> domains as **standing context**: when a change incorporates one, call it out in the Issue/PR
> and follow the pattern (and avoid the listed anti-patterns). These reflect the **Claude
> Certified Architect** exam domains and are good engineering regardless of certification.

| # | Domain | "Domain-aligned" means |
|---|--------|------------------------|
| **D1** | **Agentic Architecture & Orchestration** | Build on a real Agent SDK. Agentic loops **terminate on `stop_reason`**, never by parsing prose (an iteration cap is a safety net, not the exit condition). Prefer **hub-and-spoke** (orchestrator → focused subagents) with clean task decomposition. Enforce critical rules with **runtime hooks**, not prompt text. |
| **D2** | **Tool Design & MCP Integration** | **≤ 5 well-described tools per agent.** Tool descriptions are precise and unambiguous. Tools return **structured errors** (`isError`, `errorCategory`, `isRetryable`, plus context) and distinguish "access failed" from "no results." Expose data via a curated MCP server rather than dumping raw access. |
| **D3** | **Claude Code Config & Workflows** | Maintain a `CLAUDE.md` hierarchy, custom **commands** + **skills**, **hooks**, CI gating, and use **plan mode** for risky work and **batch** for bulk. (This whole playbook is a D3 artifact.) |
| **D4** | **Prompt Engineering & Structured Output** | Get structure via **`tool_use` + JSON schema**, not free-text parsing. Add a **validation-retry loop**, **few-shot** examples, and **per-field confidence**. Make outputs machine-checkable. |
| **D5** | **Context Management & Reliability** | Carry **provenance** from every model-derived field back to its source record `id`. Use **structured escalation / human-review queues**. **No silent error suppression.** Track metrics **per category / per source**, not one aggregate number. |

**Anti-pattern checklist — use as PR-review criteria for any LLM-touching change:**

- [ ] Loops terminate on **`stop_reason`**, not by reading prose or hitting a hard cap.
- [ ] Critical business rules enforced with **programmatic hooks**, not prompt wording.
- [ ] Escalation uses **structured criteria** (complexity, policy gaps) — never the model's
      self-reported confidence or sentiment.
- [ ] Tools return **structured errors** and separate "failed" from "empty."
- [ ] **≤ 5 tools per agent.**
- [ ] Multi-pass / reviewer agents run in a **separate session/context** to avoid reasoning bias.
- [ ] Metrics tracked **per source / per category**, not a single aggregate.
- [ ] Model outputs that drive decisions carry **provenance** to their source.

When in doubt, prefer the domain-aligned pattern even if a shortcut exists — the shortcut is
usually one of the anti-patterns above.

---

## 7. Claude Code configuration kit (`.claude/`)

Reusable scaffolding that makes the agent productive *and* safe in any repo:

- **`settings.json`** — `permissions.allow` (allowlist the safe, frequent commands so the agent
  isn't prompted constantly) and `hooks` (wire the `PreToolUse` branch-protection hook for both
  `Bash` and `PowerShell` matchers). The harness enforces these — the model can't bypass them.
- **`commands/`** — slash commands for repeatable SDLC steps: `/branch` (named, slugified
  branch), `/pr` (tier-aware PR with test plan), `/git-commit`, `/changelog`, `/status`.
- **`skills/`** — encapsulated procedures (e.g. build, regenerate generated files, run a
  pipeline). Mark a skill `disable-model-invocation: true` when it must be human-triggered only.
- **`agents/` (subagents)** — scoped, often **read-only** reviewers that run in a **separate
  context**. A "data-quality reviewer" or "pre-build safety checker" subagent (tools limited to
  `read`/`search`/`grep`) models the separate-session review pattern (D5) and produces a
  PASS/FAIL report with `file:line` evidence.

**Memory rules for agents:**
- Never store secrets, keys, or credentials in any memory, instruction, or prompt.
- Re-read volatile repo facts (schemas, column names, thresholds, config) from the **current
  branch** — never assume them from memory; memory reflects a past state.
- If a memory names a file/flag/function, **verify it still exists** before acting on it.

---

## 8. What counts as a guardrail violation

- Pushing directly to `main`/`master`.
- Editing a Tier 3 file without a PR + human review.
- Adding secrets, passwords, or a real `.env` to any tracked file.
- Hand-editing an auto-generated file instead of regenerating it from source.
- Renaming/removing existing schema fields where only additive changes are allowed.
- Modifying CODEOWNERS, this file, CI workflows, or hooks to **reduce** review requirements.
- Self-approving or self-merging an agent-generated Tier 3 PR.

---

## 9. Adoption checklist (do this when dropping the playbook into a new repo)

- [ ] Rename this file to `AGENTS.md` at the repo root (keep the original in `docs/` if useful).
- [ ] Add/keep a `CLAUDE.md` for project-specific architecture, conventions, and commands.
- [ ] Fill the **Tier 2 / Tier 3** sections with this repo's real file paths.
- [ ] Mirror every Tier 3 path into `.github/CODEOWNERS` with a reviewer.
- [ ] Turn on **branch protection** for `main` (PR required, status checks, CODEOWNERS review,
      no force-push).
- [ ] Add the `PreToolUse` push-blocking hook and wire it in `.claude/settings.json`.
- [ ] Add a CI workflow: tests + lint + SAST + secret scan + governance-consistency, all
      least-privilege (`permissions: {}` + per-job grants) with SHA-pinned actions.
- [ ] If deploying: use **OIDC** (no stored cloud keys) with a resource-scoped deploy role.
- [ ] Add the **Agent Task** issue template and the tier-/domain-aware **PR template**.
- [ ] Enable **Dependabot** (deps + actions) and the platform's native secret scanning.
- [ ] Define your **Conventional Commit** scope vocabulary.
- [ ] Decide your stance on the **Architect domains** (§6) and reference `docs/EXAM_ALIGNMENT.md`
      if you keep the per-domain roadmap.

---

*Derived from a working AGENTS.md / CLAUDE.md governance setup. Adapt the specifics; keep the
structure: tiers → SDLC → platform enforcement → CI/CD → security → agentic-AI standards.*
