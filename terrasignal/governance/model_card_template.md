# Model Card — {model_name} v{version}

**Status:** {status} · **Registered:** {created_at} · **Git SHA:** `{git_sha}`

## Intended use
{intended_use}

## Out-of-scope uses (explicit)
{out_of_scope}

## Training window & data
- Training snapshot: `{training_snapshot_uri}`
- DQ report: `{dq_report_uri}`
- Eval-set hash: `{eval_set_hash}`
- Split policy: **time-based only** (train ≤ T, evaluate on later months). Random
  splits leak market regime and are forbidden for this domain.

## Evaluation (candidate vs baselines, same eval window)
{metrics_table}

## Known failure modes
{failure_modes}

## Owner & review
- Owner: {owner}
- Next review due: {review_date}
