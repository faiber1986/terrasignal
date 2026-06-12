# Model Card — terrasignal-risk-scorer v1

**Status:** PendingManualApproval · **Registered:** 2026-06-12T02:04:56+00:00 · **Git SHA:** `unversioned`

## Intended use
Rank commercial tenants by probability of default/material delinquency within 6 months, to prioritize credit & collections outreach. Decision support only.

## Out-of-scope uses (explicit)
- Eviction decisions or lease-application screening (fair-housing-adjacent boundary, even in commercial).
- Automated credit denial of any kind.
- Tenants with <3 months payment history (insufficient signal).

## Training window & data
- Training snapshot: `C:\Users\andre\Documents\Proyectos inmobiliarios\terrasignal\data\snapshots\560405d9-e3e6-44f0-b03b-420e22f6e393`
- DQ report: `C:\Users\andre\Documents\Proyectos inmobiliarios\terrasignal\data\dq\dq_report_560405d9-e3e6-44f0-b03b-420e22f6e393.json`
- Eval-set hash: `f6bede75faaea21da63cdd5f6778eeab99a279704575ce6d41f7aaef0885db69`
- Split policy: **time-based only** (train ≤ T, evaluate on later months). Random
  splits leak market regime and are forbidden for this domain.

## Evaluation (candidate vs baselines, same eval window)
| Metric | Candidate | Baselines |
|---|---|---|
| pr_auc | 0.8034 | logistic: 0.7403 |
| roc_auc | 0.9752 | logistic: 0.9667 |
| brier | 0.0134 | logistic: 0.0565 |
| precision_at_decile | 0.3519 | logistic: 0.3374 |
| base_rate | 0.0376 | — |
| median_lead_time_days | 153.0000 | — |

## Known failure modes
- Tenants with <12 months history score near the base rate.
- Sudden macro shocks shift the calibration; watch the Brier monitor.
- Defaults engineered to look like slow payers are detected late.

## Owner & review
- Owner: ml-platform@terrasignal.local
- Next review due: 2026-09-01
