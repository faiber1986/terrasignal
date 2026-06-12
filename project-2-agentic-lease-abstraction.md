# Project 2 — LedgerLens: Agentic Lease Abstraction, CAM Reconciliation & Automated Financial Reporting

> **System Design Document — for implementation with Claude Code**
> Target reviewer: Staff AI/ML Engineer, Real Estate Tech.
> Scope: Document processing (NLP/LLMs) + complex agentic system (LangGraph) + operational efficiency, on top of a governed SQL system of record. Builds on the MLOps backbone from Project 1.

---

## 1. Business Problem

Three operational sinkholes in commercial property management, all document-driven:

1. **Lease abstraction.** Every executed lease (60–200 pages of amendments, exhibits, estoppels) must be abstracted into ~80 structured fields (rent schedule, escalations, CAM caps, renewal options, co-tenancy, termination rights). Today: paralegals at 4–8 hours per lease, ~$150–400/lease outsourced, with 5–10% field error rates that surface later as billing disputes.
2. **CAM/OpEx reconciliation leakage.** Annual common-area-maintenance reconciliations require checking invoiced expenses against each lease's *specific* exclusions, caps, gross-up clauses, and base years. Errors run both directions: under-billing (direct NOI leakage, typically 1–3% of recoverable expenses) and over-billing (tenant disputes, legal exposure).
3. **Monthly financial reporting.** Analysts spend 2–4 days/month assembling variance commentary from the GL — copy-pasting numbers into Word and explaining them.

**LedgerLens** is a human-in-the-loop agentic system:

- **Abstraction pipeline:** ingests lease PDFs → produces structured, *page-and-bounding-box-cited* abstracts → human review UI → writes to the SQL system of record only after approval.
- **CAM Reconciliation agent:** LangGraph multi-agent workflow that audits a property's annual reconciliation against abstracted clause data, with every finding traceable to a clause citation and a SQL computation.
- **Reporting agent:** drafts monthly owner reports where **every number comes from SQL, never from the LLM** (the LLM writes prose around computed figures).

### Business Success Metrics

- **Abstraction cost/time:** ≤ 45 minutes of human review per lease (vs. 4–8 hours), measured in the review UI; ≥ 95% of fields accepted without edit on the steady-state corpus.
- **CAM recovery:** identified billing discrepancies worth ≥ 0.5% of annual recoverable expenses in the pilot portfolio (this is the dollar number that sells the project), with **zero** over-billing findings shipped to tenants without human sign-off.
- **Reporting cycle:** monthly report draft in < 30 minutes of compute, analyst editing time −60%.
- **Trust metric:** field-level extraction precision ≥ 98% on the critical-field subset (rent schedule, caps, base years) at the chosen confidence threshold — measured on a frozen, versioned golden set (§5.4).

ML proxy metrics: extraction F1 per field type; citation validity rate (does the cited bbox actually contain the value) ≥ 99%; reconciliation finding precision ≥ 90% on seeded-error test properties.

---

## 2. Architecture Overview

```
            Lease PDFs / invoices / GL extracts
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│ S3 (raw docs, immutable, versioned)                                  │
│   │                                                                  │
│   ▼                                                                  │
│ Document Pipeline (Step Functions)                                   │
│   1. Textract OCR (text + tables + geometry)                         │
│   2. HF LayoutLMv3 page/section classifier  ──── SageMaker endpoint  │
│   3. Chunking + bge embeddings (batch)      ──── SageMaker batch     │
│   4. Bedrock (Claude) field extraction w/ structured output + cites  │
│   5. Deterministic validators (Pydantic + SQL cross-checks)          │
│   → staging tables (Postgres) with provenance per field              │
│                          │                                           │
│                          ▼                                           │
│            Human Review UI (Next.js)  ── approve/edit ──┐            │
│                                                         ▼            │
│                     System of Record (Postgres: leases, clauses,     │
│                     rent_schedules, recovery_terms — Project 1 schema│
│                     extended)                                        │
│                          │                                           │
│        ┌─────────────────┼──────────────────────┐                    │
│        ▼                                        ▼                    │
│  LangGraph: CAM Reconciliation Agent     LangGraph: Reporting Agent  │
│  (planner → clause-retriever →           (SQL analyst → narrative    │
│   SQL calculator → auditor →             writer → fact-checker →     │
│   findings compiler → HITL gate)         compiler → HITL gate)       │
│        │                                        │                    │
│        └────────► FastAPI backend ◄─────────────┘                    │
│                   (ECS Fargate)                                      │
│  Langfuse (self-hosted): traces, evals, prompt versions              │
└──────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
               Next.js 15 frontend: review workbench,
               reconciliation findings, report editor, governance console
```

**Role of each mandated technology:**

- **PyTorch/HuggingFace:** `LayoutLMv3-base` fine-tuned for page/section classification (cover page, rent schedule, CAM clause, exhibit, amendment, estoppel...). This is the routing brain: it tells the extractor *where* to look so we don't shove 200 pages into a context window. Fine-tuned on SageMaker (`ml.g5.2xlarge`), registered in the Model Registry, served on a SageMaker endpoint. Also `bge-base-en` for clause retrieval embeddings (batch transform).
- **Amazon Bedrock (Claude Sonnet):** field extraction with tool-use/structured output, and narrative generation in the reporting agent. Prompts versioned as code (§6.3).
- **LangGraph:** both agents. Chosen over a single-prompt approach because the workflows have genuine state, branching, retries, and human-gate semantics (checkpointed graphs, resumable after human input).
- **Polars/NumPy:** GL ingestion and the deterministic CAM calculation engine (pro-rata shares, caps with compounding, gross-ups, base-year math). **All money math is Polars/NumPy code with unit tests — the LLM never does arithmetic.**
- **Scikit-learn/XGBoost:** a small but real production model — the **review-priority triage model** (XGBoost): predicts P(human will edit this extracted field) from confidence scores, field type, document quality features, and historical edit data. Output drives the review queue order and the auto-accept threshold policy (§7.2). Trained/registered/monitored on the Project 1 SageMaker backbone.
- **SageMaker:** endpoints for LayoutLM + triage model, batch transform for embeddings, Model Registry + Model Monitor reused from Project 1 (one MLOps backbone, two projects — say this in the README, it's the realistic enterprise pattern).

---

## 3. Data Layer — SQL Before LLM, Always

### 3.1 Schema extensions (Postgres)

```sql
documents(doc_id PK, s3_uri, sha256, doc_type, property_id FK, lease_id FK NULL,
          page_count, ocr_status, uploaded_by, uploaded_at)
doc_pages(page_id PK, doc_id FK, page_no, layout_class, layout_confidence)
extracted_fields(field_id PK, doc_id FK, lease_id FK, field_name, value_raw,
                 value_typed JSONB, confidence, page_no, bbox JSONB,
                 extractor_version, prompt_version, status
                 CHECK (status IN ('pending','approved','edited','rejected')),
                 reviewed_by, reviewed_at)
rent_schedules(lease_id FK, period_start, period_end, base_rent_psf, source_field_id FK)
recovery_terms(lease_id FK, expense_pool, pro_rata_share, base_year, cap_pct,
               cap_type, gross_up_pct, exclusions JSONB, source_field_id FK)
gl_entries(entry_id PK, property_id FK, account_code, period, amount, vendor, memo, ...)
cam_reconciliations(recon_id PK, property_id FK, year, status, ...)
recon_findings(finding_id PK, recon_id FK, lease_id FK, finding_type, delta_amount,
               explanation, clause_citations JSONB, computation_trace JSONB,
               status, approved_by)
```

Note `source_field_id` on the structured tables: **every value in the system of record points back to the extracted field that produced it, which points back to a page + bounding box in an immutable PDF.** That chain is the whole governance story.

### 3.2 Validation gates (the "SQL is 80%" section)

Nothing the LLM produces is trusted until it survives four deterministic gates:

1. **Type/parse gate (Pydantic):** every field has a typed schema (`Money`, `Pct`, `DateRange`, enum clause types). Unparseable → auto-reject, never silently coerced.
2. **Intra-document consistency (SQL/Polars):** rent schedule periods must tile the lease term with no gaps/overlaps (`SUM(period) = term`); escalations must reproduce the schedule within $0.01; pro-rata share ≈ unit RSF / property RSF (±0.5%) against the `units` table; cap math is recomputable.
3. **Cross-source reconciliation:** extracted base rent vs. actual `payments` history for in-place leases (±2% → else flag "extraction vs. billing mismatch" — these flags are *themselves valuable findings*, often catching real billing errors, and the demo should show one).
4. **GL quality gate before any reporting agent run:** Polars + pandera contracts on GL extracts — account codes valid against chart of accounts, periods complete, trial balance ties to zero, duplicate-entry detection (same vendor+amount+period hash). Reporting agent refuses to run on a failed gate; it returns the dq report instead of a report. **An agent that declines to work on bad data is the feature, not a bug.**

### 3.3 Agent ↔ SQL contract

Agents never get raw SQL access. They call **whitelisted, parameterized query tools** (FastAPI-internal functions exposed as LangGraph tools), each returning typed Pydantic results:

```python
@tool
def get_recovery_terms(lease_id: UUID) -> RecoveryTerms: ...
@tool
def compute_cam_charge(lease_id: UUID, year: int) -> CamComputation:
    """Deterministic Polars engine. Returns amount + full computation_trace."""
@tool
def get_gl_expense_pool(property_id: UUID, year: int, pool: str) -> ExpensePool: ...
@tool
def get_variance(property_id: UUID, period: str, account_group: str) -> VarianceResult: ...
```

No string-built SQL from LLM output, ever. Read-only DB role for agent tool connections. This kills both prompt-injection-to-SQL and hallucinated joins in one move.

---

## 4. Document Pipeline (Step Functions)

1. **Ingest:** PDF → S3 (immutable, SHA-256 recorded). Dedup on hash.
2. **OCR:** Textract (text + tables + word geometry). Raw output archived to S3.
3. **Layout classification:** LayoutLMv3 endpoint classifies every page; sections assembled from contiguous page classes. Low-confidence pages (< 0.7) routed to "full extraction" mode (more expensive, more careful prompting).
4. **Targeted extraction:** for each of ~80 fields, a field-group prompt receives only the relevant sections (plus retrieval over chunk embeddings as fallback for fields not found in expected sections). Claude must return, per field: `value`, `confidence`, `page_no`, `quote`, `bbox` (snapped to nearest Textract word geometry containing the quote). A **citation validator** re-checks the quote exists at the claimed location; invalid citation → field rejected regardless of how plausible the value looks.
5. **Validation gates** (§3.2) → `extracted_fields` staging with status `pending`.
6. **Triage model** scores fields → review queue ordering + auto-accept policy (§7.2).
7. **Human review** in the workbench → approval writes to system-of-record tables in one transaction with audit events.

**Amendment handling (the real-world hard part, do not skip):** documents are processed in execution-date order per lease; later amendments produce field *supersessions*, not overwrites — `extracted_fields` keeps the full chain and the system of record materializes "current effective terms" via a SQL view. The demo corpus must include at least one lease with two amendments that change the rent schedule and one that modifies a CAM cap.

---

## 5. Agentic Systems (LangGraph)

### 5.1 CAM Reconciliation Agent

Graph (checkpointed in Postgres, resumable):

```
plan → for each lease in property:
   retrieve_terms (SQL tool) → compute_expected (deterministic engine)
   → compare_to_billed (SQL tool) → IF |delta| > materiality:
        clause_audit (retrieval over clause text + Bedrock: "does any clause
        justify this delta? cite or say no") → classify_finding
→ compile_findings → human_gate (interrupt) → on approval: persist + draft tenant letters
```

Design rules:
- **LLM roles are bounded:** interpreting clause language and drafting explanations. Deltas come from the Polars engine; classification thresholds from config.
- Every finding stores `computation_trace` (inputs, formula steps, intermediate values as JSON) + `clause_citations` (doc/page/bbox). The UI renders the trace as a worked example — an auditor can check it with a calculator.
- **Adversarial self-check node:** a second Bedrock pass attempts to *refute* each finding ("argue the billing was correct, citing clauses"). Findings that survive get `challenged=true` metadata; findings refuted with a valid citation are downgraded to "needs human analysis". Cheap, and it measurably cuts false positives.
- Hard stop: over-billing findings (tenant owed money) can never auto-generate outbound letters; they queue for legal review (config-enforced edge in the graph, not a prompt instruction).

### 5.2 Reporting Agent

```
gl_quality_gate → variance_scan (SQL tools, materiality thresholds from config)
→ for each material variance: context_gather (work orders, lease events, recon
  findings via SQL tools) → narrative_writer (Bedrock)
→ fact_checker → compiler (assembles report, numbers injected from SQL results
  by template, not by the LLM) → human_gate → publish PDF + archive
```

- **Fact-checker node:** parses every numeric token in the narrative and verifies it exists in the structured tool outputs for that section (normalized matching: currency, %, rounding tolerance). Unverifiable number → that paragraph regenerated with the violation in context; two failures → paragraph replaced by template text + flag. Fact-check pass rate is a tracked eval metric.
- Tone/structure controlled by versioned report templates; the LLM fills bounded slots.

### 5.3 Why LangGraph specifically
Checkpointing (human gates can pause a run for days), explicit state machine (auditable trajectory: which nodes ran, with what inputs/outputs — exported to Langfuse traces and linked from findings), and deterministic retry semantics per node. A single mega-prompt cannot offer any of that; the README should include this justification.

### 5.4 Evaluation harness (treat agents like models)
- **Golden set:** 25 real-structure synthetic leases (generated, then human-verified) with ground-truth abstracts; 5 properties with seeded reconciliation errors (both directions); 6 months of synthetic GL with known variances and causes.
- CI runs the harness on every prompt/graph/model change: field-level F1, citation validity, finding precision/recall, fact-check pass rate, cost and latency per document. Regression > 1pp on critical fields blocks merge.
- Golden set is versioned (DVC) and frozen per release; additions go through review like code.

---

## 6. MLOps & LLMOps — Lifecycle Automation

### 6.1 Classical models (LayoutLM, triage XGBoost)
Same backbone as Project 1: SageMaker Pipelines → metric gates → Model Registry (`ledgerlens-layout-classifier`, `ledgerlens-review-triage`) → manual approval → blue/green endpoint deploy. Model Monitor on the LayoutLM endpoint watches **input drift** (page image statistics, OCR confidence distribution — new scanner or new document template shows up here first) and classification confidence drift (PSI > 0.2 alarm → retrain trigger with newly labeled pages from the review workbench, which doubles as a labeling tool: every human correction is training data — the data flywheel, label it as such in the README).

### 6.2 Feature store
Triage model features (document quality stats, per-field historical edit rates, extractor confidence aggregates) live in SageMaker Feature Store with point-in-time semantics — edit-rate features as of extraction time, no peeking at the review outcome.

### 6.3 Prompt & graph versioning
- Prompts are code: `/agents/prompts/*.j2`, semver, changelog, rendered hash recorded on every `extracted_fields` row and agent run (`prompt_version` column — already in schema).
- Bedrock model ID pinned per release; model upgrades go through the eval harness exactly like a prompt change. **A model swap is a deployment, not a config tweak.**
- Langfuse: traces for every agent run (node-level latency/cost/tokens), online eval scores, prompt-version comparison dashboards.

### 6.4 Drift for LLM components
No labels in real time, so monitor proxies: extraction confidence distribution per field type, human edit rate (7-day rolling vs. baseline — the truest signal), citation-validity rate, fact-check failure rate, retrieval score distributions. Edit rate +5pp sustained for 3 days → alarm → pull worst documents into an investigation queue → harvest corrections → retrain/refine. The runbook (`/docs/runbooks/llm_drift.md`) distinguishes *data drift* (new lease template in the corpus) from *model drift* (Bedrock-side behavior change) and prescribes different responses.

---

## 7. Backend & Frontend

### 7.1 FastAPI backend (ECS Fargate)
FastAPI + Pydantic v2, SQLAlchemy 2 async, S3 presigned uploads, Step Functions trigger/poll, LangGraph runtime (Postgres checkpointer) executed in worker processes (SQS-fed) so agent runs never block the API, SSE endpoints streaming agent progress to the UI, Cognito JWT + roles (`reviewer`, `controller`, `legal`, `admin`).

```
POST /api/v1/documents                     # presigned upload → pipeline kickoff
GET  /api/v1/leases/{id}/abstract          # fields + status + citations
POST /api/v1/fields/{id}/review            # approve/edit/reject (+reason)
POST /api/v1/reconciliations               # start CAM agent for property+year
GET  /api/v1/reconciliations/{id}/stream   # SSE: node-by-node progress
POST /api/v1/reconciliations/{id}/approve  # human gate resolution
POST /api/v1/reports/monthly               # start reporting agent
GET  /api/v1/governance/lineage/{value_id} # field → doc page → pixel chain
GET  /api/v1/governance/runs/{run_id}      # full agent trajectory
```

### 7.2 Review workbench (the make-or-break UX)
Next.js 15 + TypeScript, `react-pdf` viewer with **bbox highlight overlays**, TanStack Query, shadcn/ui, OpenAPI-generated types shared with backend.

- **Side-by-side review:** extracted field list (ordered by triage score, riskiest first) ↔ PDF auto-scrolled to the cited location with the quote highlighted. Keyboard-first (accept `a`, edit `e`, reject `r`, next `j`) — review throughput is the product.
- **Auto-accept policy, explicit and governed:** fields with triage-predicted edit probability < 1% *and* extractor confidence > 0.98 *and* field not in the critical set (rent, caps, base years — **always human-reviewed, no exceptions**) are batch-accepted with a distinct audit status (`auto_accepted`) and remain spot-check-sampled at 5%. The policy thresholds live in config, are shown in the governance console, and changing them is an audited event.
- **Reconciliation findings view:** findings table → expandable computation trace + clause citations → approve / downgrade / send-to-legal.
- **Report editor:** draft with verified numbers locked (rendered as non-editable tokens with lineage tooltips), prose editable; fact-check badge per paragraph.
- **Governance console:** agent run explorer (trajectories, costs), prompt versions in production, eval-harness trends, drift status, auto-accept policy and its history.

---

## 8. Model Governance (financial-risk lens)

This system writes to the books and to tenant communications. Governance is structural, not a PDF.

1. **Field-level lineage (provenance chain):** any value in `rent_schedules`/`recovery_terms` → `source_field_id` → page + bbox + quote in an immutable, hash-verified PDF → extractor + prompt version → reviewer identity + timestamp. The lineage endpoint returns this chain; the UI renders it in two clicks. *This is the demo's money shot.*
2. **Separation of computation and narration:** documented invariant — LLMs interpret text and write prose; Polars/SQL compute money; the fact-checker enforces the boundary at runtime. Include the invariant as an ADR (`/docs/adr/003-llm-never-computes.md`).
3. **Human gates are graph edges, not policies:** over-billing findings → legal queue; critical fields → mandatory review; report publishing → controller sign-off. Encoded in LangGraph structure and role-checked API endpoints, so they cannot be skipped by prompt injection or an enthusiastic model.
4. **Materiality & thresholds as governed config:** reconciliation materiality, auto-accept thresholds, variance thresholds — versioned config, changes audited with author + reason, displayed in the console.
5. **Immutable audit trail:** append-only `audit_events` covering every review action, gate resolution, threshold change, prompt deployment, model approval. Agent trajectories archived (Langfuse + S3) with retention policy.
6. **Adverse-action boundary:** the system never auto-sends anything to a tenant; drafts only. Stated in the model card and enforced in code (no outbound integration exists — absence of capability is the strongest control).
7. **Quarterly model risk review:** auto-generated pack — eval-harness trends, edit-rate by field, auto-accept spot-check results, fact-check failures, incident log — with named-reviewer sign-off recorded as an audit event.
8. **Kill switches:** per-component flags (disable auto-accept; pause agents; force full-human review) flippable without deploy; tested in CI.

---

## 9. Repository Layout & Delivery Plan

```
ledgerlens/
├── db/migrations/                # schema incl. provenance + audit tables
├── pipeline/                     # Step Functions defs, Textract, citation validator
│   ├── layout_classifier/        # LayoutLMv3 fine-tune (PyTorch/HF, SageMaker)
│   └── extraction/               # field schemas, prompts, gates
├── engine/                       # Polars/NumPy CAM + variance math (heavily unit-tested)
├── agents/
│   ├── reconciliation/           # LangGraph graph, tools, adversarial check
│   ├── reporting/                # graph, fact-checker, templates
│   └── prompts/                  # versioned .j2 prompts + changelog
├── triage/                       # XGBoost review-priority model (SageMaker)
├── evals/                        # golden set (DVC), harness, CI gates
├── backend/                      # FastAPI, SSE, workers, RBAC
├── frontend/                     # Next.js review workbench + consoles
├── governance/                   # ADRs, model cards, runbooks, review-pack generator
├── infra/                        # Terraform
└── docs/                         # architecture, demo script
```

**Build order:**
1. Schema + synthetic corpus generator (leases with amendments, seeded extraction traps, GL with known variances) + DQ gates.
2. Document pipeline through extraction with citations → staging tables (single lease end-to-end).
3. Review workbench with PDF/bbox overlay → first approved abstract in the system of record.
4. CAM engine (pure functions, exhaustive tests) → reconciliation agent → findings UI with computation traces.
5. Reporting agent + fact-checker + report editor.
6. Triage model + auto-accept policy; LayoutLM fine-tune replacing the heuristic page router; eval harness in CI.
7. Drift monitoring, governance console, quarterly pack generator, demo script.

**Out of scope (explicitly):** e-signature/lease execution workflows, accounting-system writeback (export files only), residential leases, training a custom extraction LLM (Bedrock + retrieval + validation beats a fine-tune at this corpus size — write the ADR explaining why; knowing when *not* to fine-tune is the senior signal).

---

## 10. How the Two Projects Read Together

Project 1 proves you can build and **operate** classical ML with a real lifecycle (feature store → registry → drift → retrain). Project 2 proves you can put LLMs and agents into a financial workflow **without giving up determinism, traceability, or control** — reusing the same MLOps backbone. Progression: tabular prediction → document intelligence → governed multi-agent automation, all on one CRE data foundation where SQL quality gates stand between every model and the business.
