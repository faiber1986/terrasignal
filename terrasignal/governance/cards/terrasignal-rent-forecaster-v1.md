# Model Card — terrasignal-rent-forecaster v1

**Status:** PendingManualApproval · **Registered:** 2026-06-12T02:53:24+00:00 · **Git SHA:** `unversioned`

## Intended use
Estimate achievable base rent ($/SF/yr) at renewal, 6–18 month horizon, as a pricing range (p10/p50/p90) for asset managers. A human prices the lease.

## Out-of-scope uses (explicit)
- Binding price commitments without human review.
- Thin submarkets with <5 trailing comps (range degrades; UI flags low comp count).
- Asset classes outside office/retail/industrial.

## Training window & data
- Training snapshot: `C:\Users\andre\Documents\Proyectos inmobiliarios\terrasignal\data\snapshots\4a0e42cc-5b2c-40dd-9e44-614518fe5d6e`
- DQ report: `C:\Users\andre\Documents\Proyectos inmobiliarios\terrasignal\data\dq\dq_report_4a0e42cc-5b2c-40dd-9e44-614518fe5d6e.json`
- Eval-set hash: `f0e137de6d0c6f8d82f9211fb54d40ad6728fbb46ca5e5204d22a9af28ec1de4`
- Split policy: **time-based only** (train ≤ T, evaluate on later months). Random
  splits leak market regime and are forbidden for this domain.

## Evaluation (candidate vs baselines, same eval window)
| Metric | Candidate | Baselines |
|---|---|---|
| mape_p50 | 0.0446 | ridge: 0.0525, comp_median: 0.0945 |
| rmse_p50 | 1.4698 | — |
| p10_p90_coverage | 0.5209 | — |
| n_eval | 455.0000 | — |

## Known failure modes
- Thin submarkets (low comp_count_6m) widen true uncertainty beyond the band.
- Regime changes (e.g. office post-2023) are learned only after comps arrive.

## Owner & review
- Owner: ml-platform@terrasignal.local
- Next review due: 2026-09-01
