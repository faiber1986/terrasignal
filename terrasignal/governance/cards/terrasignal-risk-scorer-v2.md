# Model Card — terrasignal-risk-scorer v2

**Status:** PendingManualApproval · **Registered:** 2026-06-12T02:53:15+00:00 · **Git SHA:** `unversioned`

## Intended use
Rank commercial tenants by probability of default/material delinquency within 6 months, to prioritize credit & collections outreach. Decision support only.

## Out-of-scope uses (explicit)
- Eviction decisions or lease-application screening (fair-housing-adjacent boundary, even in commercial).
- Automated credit denial of any kind.
- Tenants with <3 months payment history (insufficient signal).

## Training window & data
- Training snapshot: `C:\Users\andre\Documents\Proyectos inmobiliarios\terrasignal\data\snapshots\4a0e42cc-5b2c-40dd-9e44-614518fe5d6e`
- DQ report: `C:\Users\andre\Documents\Proyectos inmobiliarios\terrasignal\data\dq\dq_report_4a0e42cc-5b2c-40dd-9e44-614518fe5d6e.json`
- Eval-set hash: `a9718afb1e472817ff91de7e9cf50af203cd0fe572b023c8412a0d318b2de2d4`
- Split policy: **time-based only** (train ≤ T, evaluate on later months). Random
  splits leak market regime and are forbidden for this domain.

## Evaluation (candidate vs baselines, same eval window)
| Metric | Candidate | Baselines |
|---|---|---|
| pr_auc | 0.4840 | logistic: 0.4803 |
| roc_auc | 0.8932 | logistic: 0.9060 |
| brier | 0.0180 | logistic: 0.1163 |
| precision_at_decile | 0.1968 | logistic: 0.1968 |
| base_rate | 0.0273 | — |
| median_lead_time_days | 153.0000 | — |

## Known failure modes
- Tenants with <12 months history score near the base rate.
- Sudden macro shocks shift the calibration; watch the Brier monitor.
- Defaults engineered to look like slow payers are detected late.

## Owner & review
- Owner: ml-platform@terrasignal.local
- Next review due: 2026-09-01
