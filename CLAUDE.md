# CLAUDE.md — Shared Engineering Conventions

Root-level instructions for Claude Code. Governs development of both projects:

- `terrasignal/` — CRE Rent Forecasting & Tenant Risk Platform (see `project-1-cre-rent-risk-platform.md`)  
- `ledgerlens/` — Agentic Lease Abstraction & Financial Reporting (see `project-2-agentic-lease-abstraction.md`)

When a project-specific design doc conflicts with this file, **the design doc wins** for that project. When this file is silent, prefer boring, well-documented solutions over clever ones.

---

## 0\. Prime Directives (read before writing any code)

1. **LLMs never compute money.** All financial math lives in `engine/` or `features/` as pure, unit-tested Polars/NumPy functions. LLMs interpret text and write prose around numbers handed to them. If you find yourself asking Bedrock to add two numbers, stop and refactor.  
2. **No model output reaches the system of record without passing a deterministic validation gate.** Pydantic parse → SQL/Polars consistency checks → (where specified) human approval. Gates are code, not prompts.  
3. **Everything traceable.** Every prediction, extraction, agent run, and threshold change must be reconstructible: model/prompt version \+ data snapshot \+ who approved \+ when. If a feature can't be audited, it isn't done.  
4. **Synthetic data first.** Both projects run end-to-end on the synthetic corpus/generator. Never block on "real data"; never commit anything resembling real tenant PII.  
5. **Demo-able at every milestone.** Each phase in the build order must end in something that runs and can be shown. No 3-week dark tunnels.

---

## 1\. Monorepo Layout & Shared Code

/

├── CLAUDE.md                      \# this file

├── project-1-cre-rent-risk-platform.md

├── project-2-agentic-lease-abstraction.md

├── shared/                        \# the ONLY cross-project code

│   ├── core/                      \#   pydantic domain types (Money, Pct, DateRange, IDs)

│   ├── dq/                        \#   pandera/Polars contract helpers, dq\_report writer

│   ├── audit/                     \#   append-only audit\_events writer \+ schemas

│   ├── sagemaker/                 \#   registry/pipeline/monitor thin wrappers

│   └── bedrock/                   \#   client, retry, structured-output parse, numeric guard

├── terrasignal/                   \# Project 1 (layout per its design doc §9)

├── ledgerlens/                    \# Project 2 (layout per its design doc §9)

├── infra/                         \# Terraform root: shared VPC, RDS, ECR, Cognito,

│   ├── modules/                   \#   SageMaker domain; per-project stacks compose modules

│   ├── terrasignal/

│   └── ledgerlens/

└── .github/workflows/             \# CI (path-filtered per project \+ shared)

**Rules:**

- `shared/` is a versioned internal package (`uv` workspace member). Projects pin it; breaking changes bump minor version and require updating both consumers in the same PR.  
- Nothing in `terrasignal/` imports from `ledgerlens/` or vice versa. Cross-pollination goes through `shared/` or doesn't happen.  
- One Postgres instance, two databases (`terrasignal`, `ledgerlens`) plus a shared `audit` schema convention inside each. LedgerLens reads TerraSignal's lease tables via a read-only foreign data wrapper or a replicated `core_re` schema — pick FDW, document it in an ADR.

---

## 2\. Python Standards

- **Python 3.12.** Dependency management with **uv** (workspace mode). No `requirements.txt`; lockfile committed.  
- **Lint/format:** `ruff` (lint \+ format, line length 100\) \+ `mypy --strict` on `shared/`, `engine/`, `features/`; `mypy` basic elsewhere. CI fails on any violation; no `# type: ignore` without a comment explaining why.  
- **Pydantic v2 everywhere** at boundaries: API schemas, agent tool I/O, config, LLM structured outputs. Internal hot paths may use plain dataclasses/Polars.  
- **Polars over pandas.** pandas allowed only where a library forces it (e.g., SHAP plotting); convert at the boundary, never mix idioms in one module.  
- **Money:** integer cents or `Decimal` in `shared/core` `Money` type — never bare floats in the engine layer. Floats permitted inside model feature matrices only.  
- **Config:** `pydantic-settings`, 12-factor, no secrets in code; secrets via AWS Secrets Manager. Governed thresholds (materiality, auto-accept, drift PSI) live in versioned YAML under `*/config/governed/` — changes to these files require a PR label `governance-change` and produce an audit event on deploy.  
- **Logging:** `structlog`, JSON, every log line carries `request_id` / `run_id` / `model_version` where applicable. No `print`.  
- **SQL:** Alembic migrations only, hand-written, reviewed. Raw SQL in code only inside `db/queries/` as named, parameterized statements. Agents/LLMs never see or build SQL strings (LedgerLens §3.3 is the canonical pattern).  
- **Docstrings:** Google style on public functions; modules open with a 2–4 line "why this exists" header.

## 3\. TypeScript / Frontend Standards

- **Next.js 15, App Router, TypeScript strict.** RSC by default; `"use client"` only where interaction demands it.  
- **API contracts are generated, never hand-written:** `openapi-typescript` from FastAPI's OpenAPI spec in CI; a drift between backend schemas and committed types fails the build.  
- **State/data:** TanStack Query for client fetching/mutations; no Redux. Zod only for form-level validation (server contracts come from generated types).  
- **UI:** Tailwind \+ shadcn/ui. Recharts for charts. `react-pdf` for the LedgerLens workbench.  
- **Lint:** ESLint (next/core-web-vitals) \+ Prettier; CI-enforced.  
- **Accessibility floor:** keyboard operability is a feature requirement in the LedgerLens review workbench (it's the product), not a nice-to-have.

---

## 4\. Testing Strategy

Test pyramid per project, enforced by CI gates:

| Layer | Tooling | Scope & non-negotiables |
| :---- | :---- | :---- |
| **Unit** | `pytest`, `hypothesis` | All of `engine/` and `features/` at ≥95% branch coverage. Property-based tests for financial math (CAM caps, gross-ups, NPV, escalations): invariants like "schedule tiles the term", "cap never exceeded", "pro-rata shares sum to ≤ 1". Point-in-time correctness tests on synthetic fixtures for every feature definition. |
| **Data contracts** | pandera \+ custom | Every ingestion job has a test feeding deliberately dirty fixtures and asserting quarantine \+ halt behavior. The DQ layer's tests ARE the spec. |
| **Integration** | `pytest` \+ `testcontainers` (Postgres, LocalStack for S3/SQS) | API routes against a real DB; migrations applied from scratch each run; audit-event emission asserted on every state-changing endpoint. SageMaker/Bedrock mocked at the `shared/sagemaker`/`shared/bedrock` wrapper seam — never with ad-hoc `unittest.mock` sprinkled in business code. |
| **ML evaluation** | custom harness in `evals/` | Time-based splits only. Candidate vs. baseline comparison is a test (XGBoost must beat Ridge/heuristic by the doc-specified margin or the "training succeeded" assertion fails). Calibration (Brier) asserted for the risk scorer. |
| **LLM/agent evals** | golden set (DVC) \+ harness, runs in CI | Field F1, citation validity ≥99%, fact-check pass rate, finding precision on seeded-error properties. Any prompt, graph, or pinned-model-ID change triggers the full harness; regression \>1pp on critical fields blocks merge. Record cost/latency per run — trend reviewed, not gated. |
| **E2E** | Playwright | One happy-path flow per project (TerraSignal: score tenant → see SHAP → override with reason → audit entry exists. LedgerLens: upload lease → review field with bbox highlight → approve → value lands in system of record with lineage). Runs nightly \+ on release branches. |
| **Governance tests** | `pytest` | Kill switches actually kill (flag flipped → baseline mode/agents paused, asserted). Human gates cannot be bypassed via API (403s asserted per role). Lineage endpoint reconstructs a full chain for a known fixture. These run in CI like any other test — governance that isn't tested is decoration. |

**Conventions:** tests live next to code (`tests/` per package); fixtures generated by the synthetic-data generators with fixed seeds; no test hits real AWS (CI uses LocalStack \+ mocked wrappers; a separate, manually-triggered `infra-smoke` workflow exercises real SageMaker on a dev account).

---

## 5\. CI/CD & Branching

- **Trunk-based:** short-lived branches → PR → squash merge to `main`. PR template requires: what/why, test evidence, governance impact (yes/no \+ which).  
- **CI (GitHub Actions), path-filtered:** lint+typecheck → unit → contracts → integration → (if `agents/`, `prompts/`, `training/`, or `evals/` touched) eval harness → build images → generate OpenAPI types and fail on drift.  
- **CD:** merge to `main` deploys backend/frontend to the dev environment automatically. **Models and prompts never deploy on merge** — they deploy via the SageMaker Model Registry approval flow / prompt-version release flow described in the design docs. Code ships continuously; models ship deliberately.  
- **Releases:** tagged; release notes auto-list governed-config changes and model/prompt version bumps.

---

## 6\. Cross-Repo Implementation Order

Build TerraSignal's backbone first; LedgerLens reuses it. Phases are sequential; items within a phase can parallelize.

**Phase 0 — Foundations (shared)**

1. Monorepo scaffolding, uv workspace, CI skeleton, Terraform shared stack (VPC, RDS, ECR, Cognito, SageMaker domain).  
2. `shared/core` types, `shared/audit` writer, `shared/dq` helpers — with tests.  
3. Synthetic data generators for both projects (TerraSignal portfolio \+ LedgerLens document corpus), seeded, with injected dirt and traps. ✅ *Demo: dirty data goes in, quarantine report comes out.*

**Phase 1 — TerraSignal core ML loop** 4\. Schema \+ DQ views → Polars features \+ Feature Store → Risk Scorer pipeline → Registry → endpoint (TerraSignal doc §9 steps 1–2). ✅ *Demo: approved model serving calibrated scores.*

**Phase 2 — TerraSignal product** 5\. FastAPI scoring path with prediction+SHAP persistence; Next.js risk queue. 6\. Rent Forecaster \+ pricing workbench \+ Bedrock rationale (with numeric guard in `shared/bedrock`). ✅ *Demo: full pricing decision with explanation and audit trail.*

**Phase 3 — MLOps backbone completed (this is what LedgerLens inherits)** 7\. Model Monitor schedules, drift→retrain automation, blue/green approval Lambda, governance console v1, kill switch \+ tests. 8\. Clause encoder fine-tune (PyTorch/HF) \+ ablation; Pydantic AI Variance Analyst. ✅ *Demo: drift alarm fires on shifted synthetic data → retrain pipeline runs → new version awaits approval.*

**Phase 4 — LedgerLens document pipeline** 9\. Schema (provenance \+ supersession), Step Functions pipeline through Bedrock extraction with citation validator, staging tables (LedgerLens doc §9 steps 1–2). 10\. Review workbench with PDF/bbox overlay; first approved abstract reaches system of record with full lineage. ✅ *Demo: the field→page→pixel chain in two clicks.*

**Phase 5 — LedgerLens agents** 11\. CAM engine (pure functions, property-based tests) → reconciliation LangGraph agent → findings UI with computation traces and legal gate. 12\. Reporting agent \+ fact-checker \+ report editor. ✅ *Demo: seeded billing error found, traced, and blocked from auto-sending.*

**Phase 6 — LedgerLens MLOps \+ hardening** 13\. Triage XGBoost \+ governed auto-accept policy; LayoutLMv3 fine-tune replacing heuristic router — both registered/monitored on the Phase-3 backbone. 14\. Eval harness wired into CI as a merge gate; LLM drift monitors; quarterly review-pack generators for both projects; demo scripts \+ READMEs polished.

**Definition of done per phase:** demo runs from a clean clone via `make demo-<phase>`; CI green; ADRs written for decisions made; design-doc deltas (there will be some) recorded in the doc itself with a changelog entry.

---

## 7\. Documentation Conventions

- **ADRs** (`docs/adr/NNN-title.md`, per project): one per consequential decision. Already mandated: LLM-never-computes (LedgerLens), why-not-fine-tune-extraction-LLM, FDW-vs-replication, time-based-splits-only.  
- **Runbooks** for every alarm that can page a human (drift, DQ halt, endpoint rollback).  
- **READMEs are the portfolio.** Each project README: 90-second pitch, architecture diagram, business metrics with how they're measured, honest limitations section, demo GIF/script. Write for a Staff-level reviewer skimming in 5 minutes.  
- Keep prose in docs free of hype. "Beats Ridge baseline by 17% MAPE on time-split eval" outranks any adjective.

## 8\. Security & Privacy Floor

- All data synthetic; generators must not emit realistic SSNs/EINs or real company names.  
- Least-privilege IAM per service; agent DB roles read-only; no wildcard policies in Terraform (checked by `tfsec` in CI).  
- JWT auth on every non-health endpoint; RBAC enforced server-side (frontend hiding is UX, not security).  
- Bedrock/SageMaker invocations logged with payload hashes (not full payloads in app logs); full payloads only in their designated capture stores with lifecycle policies.

