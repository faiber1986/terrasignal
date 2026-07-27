#!/usr/bin/env bash
# TerraSignal backend entrypoint.
#
# Applies migrations on every boot (idempotent) and runs the seeding pipeline
# exactly once — the seven manual steps from the README, chained. The pipeline
# is expensive (synthetic portfolio + two XGBoost trainings), so it is guarded
# on whether predictions already exist rather than run on every restart.
set -euo pipefail

log() { echo "[entrypoint] $*"; }

log "waiting for the database ..."
python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ.get("TERRASIGNAL_DATABASE_URL_SYNC", "")
if not url:
    sys.exit("TERRASIGNAL_DATABASE_URL_SYNC is not set")

for attempt in range(60):
    try:
        create_engine(url, pool_pre_ping=True).connect().execute(text("SELECT 1"))
        print("[entrypoint] database is up.")
        break
    except Exception:
        time.sleep(2)
else:
    sys.exit("[entrypoint] database never became reachable")
PY

log "applying migrations ..."
alembic -c terrasignal/db/alembic.ini upgrade head

# --- one-time seeding -------------------------------------------------------
# `predictions` is populated by the final pipeline step, so a non-empty table
# means a previous boot already completed the whole chain.
NEEDS_SEED=$(python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["TERRASIGNAL_DATABASE_URL_SYNC"], pool_pre_ping=True)
with engine.connect() as conn:
    try:
        n = conn.execute(text("SELECT count(*) FROM predictions")).scalar_one()
    except Exception:
        n = 0
print("yes" if not n else "no")
PY
)

if [ "$NEEDS_SEED" = "yes" ]; then
  log "empty database — running the seeding pipeline (this takes a few minutes) ..."
  log "  1/6 generating the synthetic CRE portfolio"
  python -m terrasignal.synth
  log "  2/6 validating and loading through the DQ pipeline"
  python -m terrasignal.ingestion
  log "  3/6 training the tenant default risk scorer"
  python -m terrasignal.training.risk_scorer
  log "  4/6 training the renewal rent forecaster"
  python -m terrasignal.training.rent_forecaster
  log "  5/6 approving both models for serving"
  python -m terrasignal.training.registry
  log "  6/6 batch scoring + drift baseline"
  python -m terrasignal.training.batch_score
  python -m terrasignal.training.drift || log "WARNING: drift step failed; continuing."
  log "seeding complete."
else
  log "database already seeded — skipping the pipeline."
fi

# Bind the port the platform injects; 8000 keeps local runs unchanged.
PORT="${PORT:-8000}"
log "starting API on :${PORT}"
exec uvicorn terrasignal.backend.app.main:app --host 0.0.0.0 --port "${PORT}"
