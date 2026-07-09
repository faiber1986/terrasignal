# TerraSignal

**CRE Rent Forecasting & Tenant Default Risk Platform**

**Español disponible:** [README.es.md](README.es.md)

TerraSignal is the project in this repository: a CRE (commercial real estate) data platform that scores tenant default risk and forecasts renewal rents, built around one engineering discipline — **LLMs interpret, they never compute financial math** — and every model output that reaches a user is traceable back to a model version, a data snapshot, and — where it matters — a human approval.

For the full setup guide, screenshots, and user walkthrough of the running application, see **[terrasignal/README.md](terrasignal/README.md)**. This file is the repo-root overview.

---

## Repo layout

This repo is structured as a monorepo in anticipation of a second project, **LedgerLens** (agentic lease abstraction), which today is **design-only** — see [project-2-agentic-lease-abstraction.md](project-2-agentic-lease-abstraction.md). It has no code yet; `terrasignal/` is the only implemented project.

```
Proyectos inmobiliarios/
├── CLAUDE.md                              ← shared engineering conventions
├── project-1-cre-rent-risk-platform.md    ← TerraSignal design doc
├── project-2-agentic-lease-abstraction.md ← LedgerLens design doc (not yet built)
├── docker-compose.yml                     ← Postgres 16 (local dev)
├── pyproject.toml / uv.lock               ← Python workspace (uv)
├── shared/                                ← cross-project code: core types, audit writer, DQ helpers
└── terrasignal/                           ← TerraSignal: ML pipeline, FastAPI backend, Next.js frontend
```

`shared/` exists so that a future `ledgerlens/` project could reuse core types, the audit writer, and DQ helpers without either project importing the other directly.

## Recently added: dark mode & bilingual UI

The TerraSignal web app now ships with:

- **Dark / light theme toggle** — in the top navigation bar (sun/moon icon). Persists per-browser and defaults to your OS preference on first visit. Implemented as CSS-variable-driven Tailwind tokens, so every page and chart repaints consistently with no flash of the wrong theme on load.
- **English / Spanish UI toggle** — the `EN` / `ES` switch next to the theme toggle translates the entire application (navigation, KPI tiles, tables, forms, error states, chart labels). Persists per-browser. Dates are localized to the selected language; currency stays in USD, as this is a US CRE dataset regardless of UI language.

Both are client-side preferences (no backend involved) — see `terrasignal/frontend/src/lib/theme.tsx` and `terrasignal/frontend/src/lib/i18n.tsx`.

## Prime directives (apply to everything in this repo)

1. **LLMs never compute money.** All financial math lives in pure, unit-tested Polars/NumPy functions. LLMs write prose around numbers they're handed, never the numbers themselves.
2. **No model output reaches the system of record without a deterministic validation gate.** Pydantic parse → consistency checks → (where specified) human approval.
3. **Everything is traceable.** Every prediction, extraction, and threshold change is reconstructible: model/prompt version + data snapshot + who approved + when.
4. **Synthetic data first.** Both projects run end-to-end on generated synthetic data. No real tenant PII, ever.
5. **Demo-able at every milestone.** No multi-week dark tunnels — each build phase ends in something runnable.

See [CLAUDE.md](CLAUDE.md) for the full engineering conventions (Python/TypeScript standards, testing pyramid, CI/CD, build order).

## Quick start

TerraSignal is the only project currently implemented. Full step-by-step instructions (Docker, migrations, synthetic data generation, model training, running the API and frontend) are in **[terrasignal/README.md](terrasignal/README.md)**.

Condensed version, from the repo root:

```bash
uv sync                                                      # Python deps
docker compose up -d                                         # Postgres
uv run alembic -c terrasignal/db/alembic.ini upgrade head    # schema
uv run python -m terrasignal.synth                           # synthetic portfolio
uv run python -m terrasignal.ingestion                       # DQ-validated load
uv run python -m terrasignal.training.risk_scorer
uv run python -m terrasignal.training.rent_forecaster
uv run python -m terrasignal.training.registry               # approve models
uv run python -m terrasignal.training.batch_score             # score the portfolio
uv run uvicorn terrasignal.backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal:

```bash
cd terrasignal/frontend
npm install
npm run dev
```

Open `http://localhost:3001` and sign in with one of the demo users listed on the login screen.

## Build status

| Phase | Scope | Status |
|---|---|---|
| 0 | Monorepo scaffolding, shared types/audit/DQ helpers, synthetic data generators | ✅ Done |
| 1 | TerraSignal ML loop (features → risk scorer → registry → endpoint) | ✅ Done |
| 2 | TerraSignal product (scoring API + UI, rent forecaster, pricing workbench) | ✅ Done |
| 3 | MLOps backbone (drift → retrain automation, blue/green approval, governance console v1) | Partial — governance console (kill switch, registry, drift, audit) is live; automated retrain pipeline is not |
| 4–6 | LedgerLens (document pipeline, agents, MLOps) | Not started — design doc only, no code in this repo yet |

See [CLAUDE.md §6](CLAUDE.md#6-cross-repo-implementation-order) for the full phase breakdown.

## License

Internal / portfolio project. No license file — do not treat as open source.
