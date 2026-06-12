# Project 1 — TerraSignal: Commercial Rent Forecasting & Tenant Default Risk Platform

> **System Design Document — for implementation with Claude Code**
> Target reviewer: Staff AI/ML Engineer, Real Estate Tech.
> Scope: Predictive/tabular ML + production MLOps (model registry, feature store, drift monitoring) + full-stack web app.

---

## 1. Business Problem

Commercial property managers (office, retail, industrial portfolios of 50–500 assets) bleed money in two places:

1. **Mispriced renewals.** Asset managers anchor renewal offers on stale comps or gut feel. Underpricing 3–5% on a 100k sq ft office lease over a 5-year term is a six-figure NOI loss per lease.
2. **Late detection of tenant distress.** By the time a tenant is 60+ days delinquent, recovery options have collapsed. Early signals (payment-timing drift, rising maintenance disputes, shrinking headcount proxies) live in the data months earlier but nobody is looking.

**TerraSignal** is a decision-support platform with two supervised models:

| Model | Type | Target | Consumer |
|---|---|---|---|
| **Rent Forecaster** | Regression (XGBoost) | Achievable base rent ($/sq ft/yr) at renewal, 6–18 month horizon | Asset managers pricing renewals |
| **Tenant Risk Scorer** | Binary classification (XGBoost, calibrated) | P(default or material delinquency within 6 months) | Credit/collections, portfolio risk |

This is **decision support, not decision automation**. A human prices the lease; the model narrows the range and explains why. That distinction drives the governance design (§8).

### Business Success Metrics (the only ones that matter)

- **Renewal rent capture:** +2pp on achieved-vs-market rent across the renewal pipeline within 2 quarters (measured against a holdout group of properties priced without the tool — a real A/B, not vibes).
- **Bad-debt write-offs:** −15% on tenants flagged ≥90 days before delinquency event (precision@top-decile is the proxy ML metric; dollars recovered is the business metric).
- **Adoption:** ≥70% of renewal decisions in the pilot portfolio reference a TerraSignal forecast (tracked via audit log, §8.4).

ML proxy metrics (gates, not goals): Rent Forecaster MAPE ≤ 8% on 12-month horizon; Risk Scorer PR-AUC ≥ 0.45 with Brier score ≤ 0.08 after calibration (defaults are rare, ~3–5% base rate — accuracy is meaningless here, say so in the README).

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                              AWS Account                               │
│                                                                        │
│  Postgres (RDS)          ┌──────────────────────────────────────────┐ │
│  system of record  ───▶  │  Ingestion & Validation (Polars + SQL)   │ │
│  leases/payments/        │  scheduled ECS task, writes Parquet→S3   │ │
│  work orders/comps       └───────────────┬──────────────────────────┘ │
│                                          ▼                            │
│                          SageMaker Feature Store (offline+online)     │
│                                          │                            │
│              ┌───────────────────────────┼──────────────────────┐     │
│              ▼                           ▼                      │     │
│   SageMaker Pipeline (train)   SageMaker Pipeline (train)       │     │
│   Rent Forecaster              Risk Scorer                      │     │
│              │                           │                      │     │
│              └────────► SageMaker Model Registry ◄──────────────┘     │
│                                │ (approval gate)                      │
│                                ▼                                      │
│              SageMaker Real-time Endpoint (multi-model)               │
│                                │                                      │
│   SageMaker Model Monitor ─────┤  (data quality + drift schedules)    │
│                                ▼                                      │
│  ┌──────────────┐      ┌──────────────┐       ┌────────────────────┐  │
│  │ Amazon       │ ◄──  │ FastAPI      │  ───► │ Postgres (app DB:  │  │
│  │ Bedrock      │      │ backend      │       │ predictions, audit │  │
│  │ (Claude)     │      │ (ECS Fargate)│       │ log, feedback)     │  │
│  └──────────────┘      └──────┬───────┘       └────────────────────┘  │
│                               │                                       │
└───────────────────────────────┼───────────────────────────────────────┘
                                ▼
                     Next.js 15 (App Router) frontend
                     portfolio dashboard / lease detail / risk queue
```

**Role of each mandated technology (no decoration, each earns its place):**

- **Polars:** all feature engineering. Lease/payment data is wide and joins are heavy; Polars lazy frames + streaming keep the ETL on a single container instead of a Spark cluster. NumPy for vectorized financial math (NPV of lease cash flows, straight-lining).
- **Scikit-learn:** preprocessing pipelines (`ColumnTransformer`), isotonic calibration of the risk scorer, baseline models (regularized linear) that XGBoost must beat to ship.
- **XGBoost:** both production models. Tabular CRE data with <1M rows — gradient boosting wins; don't pretend a transformer is needed here.
- **PyTorch/HuggingFace:** one focused use — a sentence-transformer (`bge-small-en`) fine-tuned with a contrastive objective on lease clause text to produce **clause-risk embeddings** (e.g., weak termination clauses, co-tenancy clauses) that feed the Risk Scorer as 8 PCA-reduced features. Trained on SageMaker, served via batch transform (embeddings refresh nightly, no need for real-time). This is an honest, bounded use of deep learning where it adds lift; document the ablation (model with/without clause features) in the README.
- **Amazon Bedrock (Claude):** generates the **forecast rationale memo** shown in the UI — a narrative explaining the prediction using the SHAP values and comps as grounded context (LLM never invents numbers; it verbalizes numbers handed to it, §8.3).
- **Pydantic AI:** a single, small agent — the "Variance Analyst" — that, on a monthly schedule, queries pre-approved SQL views for portfolio actual-vs-forecast variances and drafts a commentary report with typed, validated output (`pydantic` schemas end to end). Agentic complexity is deliberately minimal here; Project 2 carries the heavy agentic load.
- **AWS SageMaker:** Pipelines (training DAG), Feature Store, Model Registry, Model Monitor, real-time endpoint. This project's center of gravity.

---

## 3. Data Layer — SQL Is 80% of the Job

### 3.1 Source schema (Postgres, system of record)

```sql
-- Core tables (simplified; full DDL in /db/migrations)
properties(property_id PK, market, submarket, asset_class, year_built, rsf, ...)
units(unit_id PK, property_id FK, floor, rsf, condition_grade, ...)
leases(lease_id PK, unit_id FK, tenant_id FK, commencement, expiration,
       base_rent_psf, escalation_pct, term_months, lease_type, security_deposit, ...)
lease_clauses(clause_id PK, lease_id FK, clause_type, raw_text, ...)
payments(payment_id PK, lease_id FK, due_date, paid_date, amount_due, amount_paid, ...)
work_orders(wo_id PK, unit_id FK, tenant_id FK, opened_at, closed_at, category,
            cost, tenant_initiated BOOL, dispute_flag BOOL, ...)
market_comps(comp_id PK, market, submarket, asset_class, signed_date,
             rent_psf, term_months, ti_allowance_psf, free_rent_months, source, ...)
tenants(tenant_id PK, industry_naics, credit_rating, parent_company, ...)
```

### 3.2 Validation gates — data never reaches the model dirty

Three-layer defense, all of which must pass before features are written:

**Layer 1 — SQL constraint views (in-database, versioned migrations).** Materialized views that quarantine violations instead of silently dropping them:

```sql
CREATE MATERIALIZED VIEW dq.lease_violations AS
SELECT lease_id, 'expiration_before_commencement' AS rule
FROM leases WHERE expiration <= commencement
UNION ALL
SELECT lease_id, 'nonpositive_rent' FROM leases WHERE base_rent_psf <= 0
UNION ALL
SELECT l.lease_id, 'orphan_unit' FROM leases l
LEFT JOIN units u USING (unit_id) WHERE u.unit_id IS NULL
UNION ALL
SELECT p.lease_id, 'payment_outside_term' FROM payments p
JOIN leases l USING (lease_id)
WHERE p.due_date NOT BETWEEN l.commencement AND l.expiration + INTERVAL '90 days';
```

**Layer 2 — Polars/pandera contracts (in the ingestion job).** Schema + statistical checks: dtypes, null budgets per column (e.g., `escalation_pct` ≤ 2% nulls), distribution sanity (`base_rent_psf` within [p0.5, p99.5] of trailing 24-month market window — flags fat-finger entries like $4,500/sq ft).

**Layer 3 — Cross-source reconciliation.** Sum of `payments.amount_due` per lease per month must tie to the contractual rent schedule derived from `leases` (±1%). Mismatches → quarantine table + Slack alert. This is the check that catches the upstream property-management-system bugs that actually happen.

**Hard rule:** if >2% of rows in any core table are quarantined, the pipeline halts and pages a human. No model trains on a bad snapshot. Every ingestion run writes a `dq_report.json` (rule → violation count → sample PKs) to S3, referenced by the training run (§8.2 lineage).

### 3.3 Feature engineering (Polars → SageMaker Feature Store)

Two feature groups, point-in-time correct (event-time joins, no leakage — payments features computed only from data available *as of* the prediction date):

- `tenant_risk_features` (entity: `tenant_id × as_of_month`): payment-timing stats over 3/6/12-month windows (mean days-late, **trend** in days-late via NumPy least-squares slope), dispute-flagged work-order rate, rent-to-market-rent ratio, industry NAICS distress index, security-deposit coverage months, clause-risk embedding components (8 dims).
- `lease_pricing_features` (entity: `unit_id × as_of_month`): submarket comp stats (median rent, TI allowance, free-rent months over trailing 6/12 months from `market_comps`), property vintage/condition, vacancy in building, lease term/type, effective-rent NPV features (NumPy).

Offline store (S3/Parquet) feeds training; online store serves the FastAPI scoring path at <50ms. Feature definitions live in code (`/features/definitions.py`), versioned, with unit tests asserting point-in-time correctness on synthetic fixtures.

---

## 4. Modeling

### 4.1 Rent Forecaster
- XGBoost regressor, quantile objective → ship **p10/p50/p90** so the UI shows a pricing *range*, not false precision.
- Baseline to beat: Ridge regression on the same features + naive "last comp median". If XGBoost doesn't beat both by ≥15% MAPE relative, don't ship it (record the comparison in the model card).
- Eval: time-based splits only (train ≤ T, validate on T+1..T+6 months). Random splits leak market regime; the README must say this explicitly because it's the most common interview-portfolio mistake.

### 4.2 Tenant Risk Scorer
- XGBoost classifier, `scale_pos_weight` for the ~4% base rate, then **isotonic calibration** (sklearn) on a temporally held-out fold — scores feed dollar-weighted expected-loss math, so calibration is non-negotiable.
- Eval: PR-AUC, Brier, and **lead time** (median days between first flag ≥ threshold and delinquency event) — the business metric in disguise.
- SHAP values computed at inference and persisted with every prediction (governance, §8.3).

### 4.3 Clause embedding model (PyTorch/HF)
- `bge-small-en-v1.5` fine-tuned with triplet loss: anchor = clause text, positive = same `clause_type` with adverse outcome, negative = benign. Labels bootstrapped from `clause_type` + delinquency outcomes (~5k pairs). Trained on a SageMaker `ml.g5.xlarge` training job, registered to the Model Registry like any other model, embeddings refreshed nightly via Batch Transform.

---

## 5. MLOps — Lifecycle Automation (the heart of this project)

### 5.1 Training pipeline (SageMaker Pipelines, one per model)

```
DataIngestionCheck → FeatureSnapshot → Train → Evaluate → CalibrationStep(risk only)
   → ConditionStep(metric gates) → RegisterModel(PendingManualApproval) → notify
```

- **Triggers:** weekly cron; on-demand; **automatically on drift alarm** (§5.3) — that closes the lifecycle loop.
- **Metric gates in code:** the `ConditionStep` compares candidate vs. current-production metrics on the *same* eval window. Worse candidate → pipeline ends, nothing registered, report still archived.

### 5.2 Model Registry as the single source of truth
- Model package groups: `terrasignal-rent-forecaster`, `terrasignal-risk-scorer`, `terrasignal-clause-encoder`.
- Each version carries: metrics JSON, eval-set hash, feature-group versions, training-data S3 snapshot URI, `dq_report.json` URI, git SHA, model card (§8.1).
- **Approval = deployment trigger:** EventBridge rule on `ModelApprovalStatus → Approved` fires a Lambda that updates the endpoint (blue/green via endpoint config swap, automatic rollback on CloudWatch alarm during a 30-min bake).
- Nothing reaches the endpoint without a human approval click. The approver and timestamp are part of the model version metadata.

### 5.3 Monitoring & drift
- **SageMaker Model Monitor — data quality:** hourly schedule against the training baseline (feature distributions, missing rates). Alerts on PSI > 0.2 for any top-10-importance feature.
- **Model Monitor — model quality:** ground truth arrives with lag (defaults observed at +6 months; achieved rents at signing). A nightly job joins delayed labels from Postgres to logged predictions and feeds the model-quality monitor. Degradation alarm → EventBridge → retraining pipeline trigger + Slack.
- **Prediction logging:** every endpoint call captured (Data Capture) + persisted to the app DB with feature snapshot, SHAP vector, model version. This table powers both monitoring and the audit log.
- **Drift runbook in repo** (`/docs/runbooks/drift.md`): what each alarm means, who acts, when auto-retrain is allowed vs. requires investigation (e.g., a market shock is *real* drift — retraining on it blindly is a governance event, not a cron job).

---

## 6. Backend — FastAPI (Python 3.12)

**Stack:** FastAPI + Pydantic v2, SQLAlchemy 2 (async) + Alembic, `asyncpg`, `boto3`/`aioboto3` for SageMaker Runtime + Bedrock, Redis for online-feature cache fallback, structlog JSON logging, OpenTelemetry traces. Deployed on ECS Fargate behind an ALB. AuthN via Cognito JWT, role-based scopes (`analyst`, `approver`, `admin`).

**Key endpoints:**

```
POST /api/v1/forecasts/rent            # unit_id + horizon → p10/p50/p90 + SHAP + comps used
POST /api/v1/risk/score                # tenant_id → calibrated PD + SHAP + trend
GET  /api/v1/risk/queue                # ranked watchlist (top-decile), paginated
POST /api/v1/forecasts/{id}/rationale  # Bedrock memo, grounded on stored SHAP+comps
POST /api/v1/feedback                  # analyst accepts/overrides → feedback table
GET  /api/v1/governance/audit          # filterable audit trail (approver role)
GET  /api/v1/models/active             # versions, approval metadata, monitor status
POST /api/v1/reports/variance/run      # triggers Pydantic AI Variance Analyst
```

**Scoring path:** request → fetch online features (Feature Store, Redis fallback) → SageMaker endpoint invoke → persist prediction + SHAP + model version to `predictions` table (same transaction as the response) → return. The persistence is not optional; it *is* the audit trail.

**Bedrock rationale guardrail:** the prompt receives a JSON of {prediction range, top-6 SHAP drivers, 5 nearest comps}; the system prompt forbids introducing numbers not in the payload; output is parsed into a Pydantic schema and a post-check verifies every dollar figure in the memo exists in the input payload (string-match on normalized numbers). Fail → regenerate once → fall back to template memo.

---

## 7. Frontend — Next.js 15 (App Router, TypeScript)

**Stack:** Next.js 15, React Server Components for data-heavy pages, TanStack Query for client mutations, Tailwind + shadcn/ui, Recharts, Zod (mirrors backend Pydantic schemas via generated OpenAPI types — `openapi-typescript` in CI so the contracts can't silently diverge).

**Pages:**
1. **Portfolio dashboard** — NOI-at-risk tiles, expirations timeline (18-month wall), risk-score distribution.
2. **Lease pricing workbench** — unit picker → forecast range (fan chart p10/p50/p90), comp table with map, SHAP waterfall, Bedrock rationale memo, "accept / override with reason" actions (writes to feedback + audit).
3. **Risk queue** — sortable watchlist, per-tenant score trend sparkline, days-late trajectory, drill-down to payment history.
4. **Model governance console** — active model versions, approval history, drift monitor status (green/amber/red per feature), link to model cards. This page is the portfolio differentiator: most candidates never show that they *operate* models.

---

## 8. Model Governance (financial-risk lens)

Automated predictions that touch pricing and credit are **model risk** in the SR 11-7 sense. The platform is built so every number on screen can be reconstructed and justified.

### 8.1 Model cards & inventory
Every registered version ships a model card (template in `/governance/model_card.md`): intended use, **explicit out-of-scope uses** (e.g., risk scorer must not be used for eviction decisions or lease application screening — that's a fair-housing-adjacent boundary even in commercial), training window, eval metrics by segment, known failure modes (thin submarkets, tenants <12 months of history), owner, review date. Cards render in the governance console.

### 8.2 Lineage & reproducibility
For any prediction ID, one query reconstructs: model version → training pipeline execution → data snapshot URI + hash → feature definitions git SHA → dq_report. A `make reproduce PREDICTION_ID=...` target retrains and re-scores within tolerance. If you can't reproduce a number, you don't govern it.

### 8.3 Explainability & challenge process
- SHAP persisted per prediction; UI always shows drivers next to the number.
- Analyst overrides require a structured reason code + free text; overrides are first-class data — a quarterly job reports override rate by segment (high override rate = model or trust problem; both are findings).
- Bedrock memos are labeled "AI-generated explanation" in the UI and stored with the prompt payload hash for audit.

### 8.4 Decision audit trail
Append-only `audit_events` table (who saw what score, who accepted/overrode, who approved which model version, when drift alarms fired and what action followed). No deletes; corrections are new events.

### 8.5 Performance & fairness review cadence
Quarterly review pack auto-generated (the Pydantic AI Variance Analyst drafts it): metric stability by asset class/market/tenant size, calibration plots, drift incidents, override analysis. Segment-level error disparities >1.5× flagged for review. Pack stored in S3 with the reviewer's sign-off recorded as an audit event.

### 8.6 Kill switch & fallback
Config flag flips the API to "baseline mode" (comp-median heuristics, clearly labeled in UI) without redeploying. Tested in CI.

---

## 9. Repository Layout & Delivery Plan

```
terrasignal/
├── db/migrations/            # Alembic; includes dq.* views
├── ingestion/                # Polars ETL + pandera contracts + dq report
├── features/                 # feature definitions, point-in-time tests
├── training/                 # SageMaker pipeline defs, train/eval scripts, calibration
│   └── clause_encoder/       # PyTorch/HF fine-tune + batch transform
├── deployment/               # endpoint configs, approval Lambda, blue/green, monitor schedules
├── backend/                  # FastAPI app (routers/services/schemas/tests)
├── frontend/                 # Next.js app
├── agents/variance_analyst/  # Pydantic AI agent + approved SQL views it may touch
├── governance/               # model card template, runbooks, review pack generator
├── infra/                    # Terraform (RDS, ECS, SageMaker, EventBridge, Cognito)
└── docs/                     # ADRs, architecture, drift runbook, demo script
```

**Build order (pragmatic, demo-able at every milestone):**
1. Schema + synthetic data generator (~200 properties, 3k leases, 5 yrs payments, injected distress patterns and dirty data so the DQ layer has something to catch) → DQ layer green.
2. Features + Feature Store + Risk Scorer end-to-end (pipeline → registry → endpoint).
3. FastAPI scoring + audit persistence; minimal Next.js risk queue.
4. Rent Forecaster + pricing workbench + Bedrock memos.
5. Model Monitor + drift→retrain automation + governance console.
6. Clause encoder fine-tune + ablation; Variance Analyst agent; polish + demo script.

**Out of scope (say so, it signals seniority):** multi-tenancy/SaaS billing, real PMS integrations (Yardi/MRI adapters stubbed behind an interface), residential anything, real-time streaming (nightly batch + on-demand scoring is the honest cadence for this domain).
