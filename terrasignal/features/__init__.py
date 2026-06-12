"""Feature engineering: Polars, point-in-time correct, versioned in code.

Two feature groups:
- tenant_risk_features  (entity: tenant_id × as_of_month)
- lease_pricing_features (entity: unit_id × event date)

No feature may read data with an event date after its as_of — the tests
assert this on synthetic fixtures.
"""
