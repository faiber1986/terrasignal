"""Seeded synthetic-data generator: portfolio, leases, payments, comps, clauses.

Injects (a) distress patterns the Risk Scorer must learn, (b) market rent
curves the Rent Forecaster must learn, and (c) deliberate dirt the DQ layer
must catch. Never emits realistic SSNs/EINs or real company names.
"""
