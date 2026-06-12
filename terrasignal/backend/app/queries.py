"""Named, parameterized SQL. The only raw SQL outside migrations.

Agents/LLMs never see or build these strings; they are code, reviewed like code.
"""

INSERT_PREDICTION = """
INSERT INTO predictions (prediction_id, created_at, model_name, model_version,
  entity_type, entity_id, as_of, request_id, features, output, shap, comps, baseline_mode)
VALUES (:prediction_id, :created_at, :model_name, :model_version, :entity_type,
  :entity_id, :as_of, :request_id, :features, :output, :shap, :comps, :baseline_mode)
"""

LATEST_PREDICTION_FOR_ENTITY = """
SELECT prediction_id, created_at, model_name, model_version, entity_type, entity_id,
       as_of, features, output, shap, comps, baseline_mode
FROM predictions
WHERE entity_type = :entity_type AND entity_id = :entity_id AND model_name = :model_name
ORDER BY created_at DESC
LIMIT 1
"""

PREDICTION_BY_ID = """
SELECT prediction_id, created_at, model_name, model_version, entity_type, entity_id,
       as_of, features, output, shap, comps, baseline_mode
FROM predictions WHERE prediction_id = :prediction_id
"""

RISK_QUEUE = """
WITH latest AS (
  SELECT DISTINCT ON (entity_id)
         prediction_id, entity_id, model_version, created_at, output, shap, baseline_mode
  FROM predictions
  WHERE model_name = 'terrasignal-risk-scorer' AND entity_type = 'tenant'
  ORDER BY entity_id, created_at DESC
)
SELECT l.prediction_id, l.entity_id AS tenant_id, l.model_version, l.created_at,
       l.output, l.shap, l.baseline_mode,
       t.name AS tenant_name, t.industry_naics, t.credit_rating
FROM latest l
JOIN tenants t ON t.tenant_id = l.entity_id
ORDER BY (l.output->>'pd')::float DESC
LIMIT :limit OFFSET :offset
"""

RENT_QUEUE = """
WITH latest AS (
  SELECT DISTINCT ON (entity_id)
         prediction_id, entity_id, model_version, created_at, output, baseline_mode
  FROM predictions
  WHERE model_name = 'terrasignal-rent-forecaster' AND entity_type = 'unit'
  ORDER BY entity_id, created_at DESC
)
SELECT l.prediction_id, l.entity_id AS unit_id, l.model_version, l.created_at,
       l.output, l.baseline_mode,
       u.rsf AS unit_rsf, u.floor,
       p.name AS property_name, p.submarket, p.market, p.asset_class
FROM latest l
JOIN units u ON u.unit_id = l.entity_id
JOIN properties p ON p.property_id = u.property_id
ORDER BY (l.output->>'lease_expiration') ASC
LIMIT :limit OFFSET :offset
"""

TENANT_DETAIL = """
SELECT tenant_id, name, industry_naics, credit_rating FROM tenants
WHERE tenant_id = :tenant_id
"""

TENANT_PAYMENT_HISTORY = """
SELECT p.due_date, p.paid_date, p.amount_due, p.amount_paid,
       CASE WHEN p.paid_date IS NULL THEN NULL
            ELSE (p.paid_date - p.due_date) END AS days_late,
       l.lease_id
FROM payments p
JOIN leases l USING (lease_id)
WHERE l.tenant_id = :tenant_id AND p.due_date >= :since
ORDER BY p.due_date
"""

TENANT_LEASES = """
SELECT l.lease_id, l.unit_id, l.commencement, l.expiration, l.base_rent_psf,
       l.term_months, l.lease_type, u.rsf AS unit_rsf,
       pr.name AS property_name, pr.submarket, pr.asset_class
FROM leases l
JOIN units u USING (unit_id)
JOIN properties pr ON pr.property_id = u.property_id
WHERE l.tenant_id = :tenant_id
ORDER BY l.commencement DESC
"""

TENANT_SCORE_HISTORY = """
SELECT as_of, created_at, output, model_version
FROM predictions
WHERE model_name = 'terrasignal-risk-scorer' AND entity_type = 'tenant'
  AND entity_id = :tenant_id
ORDER BY as_of, created_at
"""

INSERT_FEEDBACK = """
INSERT INTO feedback (feedback_id, prediction_id, created_at, actor, action,
  reason_code, comment, override_value)
VALUES (:feedback_id, :prediction_id, :created_at, :actor, :action,
  :reason_code, :comment, :override_value)
"""

AUDIT_TRAIL = """
SELECT event_id, occurred_at, actor, actor_role, event_type, entity_type, entity_id,
       request_id, payload
FROM audit_events
WHERE (CAST(:event_type AS text) IS NULL OR event_type = CAST(:event_type AS text))
  AND (CAST(:entity_id AS text) IS NULL OR entity_id = CAST(:entity_id AS text))
  AND (CAST(:actor AS text) IS NULL OR actor = CAST(:actor AS text))
ORDER BY occurred_at DESC
LIMIT :limit OFFSET :offset
"""

REGISTRY_ALL = """
SELECT model_version_id, model_name, version, created_at, status, metrics,
       baseline_metrics, eval_set_hash, training_snapshot_uri, dq_report_uri,
       git_sha, artifact_path, model_card_path, approved_by, approved_at
FROM model_registry
ORDER BY model_name, version DESC
"""

DRIFT_LATEST = """
WITH latest AS (
  SELECT model_name, MAX(computed_at) AS computed_at FROM drift_metrics GROUP BY model_name
)
SELECT d.model_name, d.feature_name, d.psi, d.status, d.computed_at,
       d.baseline_window, d.current_window
FROM drift_metrics d
JOIN latest l ON l.model_name = d.model_name AND l.computed_at = d.computed_at
ORDER BY d.model_name, d.psi DESC
"""

LINEAGE = """
SELECT p.prediction_id, p.created_at, p.model_name, p.model_version, p.entity_type,
       p.entity_id, p.as_of, p.features, p.output, p.baseline_mode,
       r.training_snapshot_uri, r.dq_report_uri, r.git_sha, r.eval_set_hash,
       r.metrics, r.approved_by, r.approved_at, r.model_card_path
FROM predictions p
LEFT JOIN model_registry r
  ON r.model_name = p.model_name AND r.version = p.model_version
WHERE p.prediction_id = :prediction_id
"""

FEEDBACK_FOR_PREDICTION = """
SELECT feedback_id, prediction_id, created_at, actor, action, reason_code, comment,
       override_value
FROM feedback WHERE prediction_id = :prediction_id ORDER BY created_at
"""

GET_FLAG = "SELECT value FROM runtime_flags WHERE key = :key"
SET_FLAG = """
UPDATE runtime_flags SET value = :value, updated_at = :updated_at, updated_by = :updated_by
WHERE key = :key
"""

PORTFOLIO_KPIS = """
SELECT
  (SELECT COUNT(*) FROM properties) AS n_properties,
  (SELECT COUNT(*) FROM units) AS n_units,
  (SELECT COALESCE(SUM(rsf), 0) FROM units) AS total_rsf,
  (SELECT COUNT(*) FROM leases
    WHERE commencement <= :today AND expiration > :today AND base_rent_psf > 0
  ) AS active_leases
"""

EXPIRATION_WALL = """
SELECT date_trunc('month', l.expiration)::date AS month,
       COUNT(*) AS leases_expiring,
       COALESCE(SUM(l.base_rent_psf * u.rsf), 0)::float AS annual_rent_expiring
FROM leases l
JOIN units u USING (unit_id)
WHERE l.expiration > :today AND l.expiration <= :horizon AND l.base_rent_psf > 0
GROUP BY 1 ORDER BY 1
"""

# Latest risk PD per tenant — drives the dashboard's avg PD, watchlist count and
# risk histogram (bucketed in Python so the band edges stay governed, not SQL).
PORTFOLIO_RISK_PDS = """
WITH latest AS (
  SELECT DISTINCT ON (entity_id) entity_id AS tenant_id,
         (output->>'pd')::float AS pd
  FROM predictions
  WHERE model_name = 'terrasignal-risk-scorer' AND entity_type = 'tenant'
  ORDER BY entity_id, created_at DESC
)
SELECT tenant_id, pd FROM latest
"""

# Annual contractual rent for active leases of tenants whose latest PD crosses
# the watchlist threshold — the NOI exposed to elevated default risk.
NOI_AT_RISK = """
WITH latest AS (
  SELECT DISTINCT ON (entity_id) entity_id AS tenant_id,
         (output->>'pd')::float AS pd
  FROM predictions
  WHERE model_name = 'terrasignal-risk-scorer' AND entity_type = 'tenant'
  ORDER BY entity_id, created_at DESC
)
SELECT COALESCE(SUM(l.base_rent_psf * u.rsf), 0)::float AS noi_at_risk
FROM latest x
JOIN leases l ON l.tenant_id = x.tenant_id
JOIN units u USING (unit_id)
WHERE x.pd >= :watchlist_pd
  AND l.commencement <= :today AND l.expiration > :today AND l.base_rent_psf > 0
"""

# Upside if every priced unit renews at the model's p50 vs. its in-place rent.
RENEWAL_UPSIDE = """
WITH latest AS (
  SELECT DISTINCT ON (entity_id) entity_id AS unit_id, output
  FROM predictions
  WHERE model_name = 'terrasignal-rent-forecaster' AND entity_type = 'unit'
  ORDER BY entity_id, created_at DESC
)
SELECT COALESCE(SUM(
    GREATEST((output->>'p50')::float - (output->>'current_rent_psf')::float, 0) * u.rsf
), 0)::float AS renewal_upside
FROM latest x
JOIN units u ON u.unit_id = x.unit_id
"""
