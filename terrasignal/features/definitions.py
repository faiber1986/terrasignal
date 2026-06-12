"""Feature definitions. Versioned in code; the registry records this module's
git SHA with every model version.

Point-in-time rule: a feature value for (entity, as_of) may use only rows whose
event date is <= as_of. Unpaid invoices contribute their days-late *so far*.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from terrasignal.synth.markets import NAICS_SECTORS

RATING_ORD = {"AA": 1, "A": 2, "BBB": 3, "BB": 4, "B": 5, "CCC": 6}
CONDITION_ORD = {"A": 1, "B": 2, "C": 3}
LEASE_TYPE_ORD = {"NNN": 0, "MG": 1, "FSG": 2}
ADVERSE_CLAUSES = ("early_termination", "co_tenancy", "security_substitution")

TENANT_FEATURES = [
    "days_late_mean_3m", "days_late_mean_6m", "days_late_mean_12m", "days_late_max_6m",
    "late_share_6m", "days_late_trend_6m", "unpaid_count", "dispute_rate_12m",
    "wo_count_12m", "rent_to_market", "deposit_coverage_months", "credit_rating_ord",
    "sector_distress_idx", "adverse_clause_share", "tenure_months", "n_active_leases",
    "total_monthly_due",
]
PRICING_FEATURES = [
    "comp_median_rent_6m", "comp_median_rent_12m", "comp_count_6m", "comp_median_ti_6m",
    "comp_median_free_rent_6m", "property_age", "condition_ord", "asset_class_ord",
    "floor", "unit_rsf", "term_months", "lease_type_ord", "building_vacancy",
    "submarket_rent_momentum",
]
ASSET_ORD = {"office": 0, "retail": 1, "industrial": 2}


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_add(d: date, months: int) -> date:
    y, m = divmod((d.year * 12 + d.month - 1) + months, 12)
    return date(y, m + 1, 1)


# --------------------------------------------------------------------------
# shared monthly pre-aggregations
# --------------------------------------------------------------------------

def comp_market_stats(comps: pl.DataFrame, months: list[date]) -> pl.DataFrame:
    """Per (submarket, asset_class, month): trailing 6m/12m comp medians."""
    out = []
    for m in months:
        for window, suffix in ((6, "6m"), (12, "12m")):
            w = comps.filter(
                (pl.col("signed_date") > _month_add(m, -window))
                & (pl.col("signed_date") <= m)
            ).group_by("submarket", "asset_class").agg(
                pl.col("rent_psf").median().alias(f"comp_median_rent_{suffix}"),
                pl.len().alias(f"comp_count_{suffix}"),
                pl.col("ti_allowance_psf").median().alias(f"comp_median_ti_{suffix}"),
                pl.col("free_rent_months").median().alias(f"comp_median_free_rent_{suffix}"),
            )
            if suffix == "6m":
                base = w
            else:
                base = base.join(
                    w.select("submarket", "asset_class", "comp_median_rent_12m"),
                    on=["submarket", "asset_class"], how="full", coalesce=True,
                )
        out.append(base.with_columns(pl.lit(m).alias("as_of_month")))
    stats = pl.concat(out, how="diagonal")
    # momentum: 6m median vs 12m median — is the submarket heating or cooling?
    return stats.with_columns(
        submarket_rent_momentum=(
            pl.col("comp_median_rent_6m") / pl.col("comp_median_rent_12m") - 1.0
        ).fill_null(0.0)
    )


def building_occupancy(leases: pl.DataFrame, units: pl.DataFrame,
                       months: list[date]) -> pl.DataFrame:
    """Per (property_id, month): share of units with an active lease."""
    unit_prop = units.select("unit_id", "property_id")
    totals = unit_prop.group_by("property_id").agg(pl.len().alias("n_units"))
    out = []
    for m in months:
        active = (
            leases.filter((pl.col("commencement") <= m) & (pl.col("expiration") > m))
            .join(unit_prop, on="unit_id", how="inner")
            .group_by("property_id")
            .agg(pl.col("unit_id").n_unique().alias("occupied"))
        )
        out.append(
            totals.join(active, on="property_id", how="left")
            .with_columns(
                occupancy=(pl.col("occupied").fill_null(0) / pl.col("n_units")),
                as_of_month=pl.lit(m),
            )
            .select("property_id", "as_of_month", "occupancy")
        )
    return pl.concat(out)


# --------------------------------------------------------------------------
# tenant risk feature group
# --------------------------------------------------------------------------

def tenant_risk_features(
    frames: dict[str, pl.DataFrame], as_of_months: list[date]
) -> pl.DataFrame:
    leases, payments = frames["leases"], frames["payments"]
    tenants, units = frames["tenants"], frames["units"]
    properties, comps = frames["properties"], frames["market_comps"]
    work_orders, clauses = frames["work_orders"], frames["lease_clauses"]

    lease_meta = (
        leases.join(units.select("unit_id", "property_id", pl.col("rsf").alias("unit_rsf")),
                    on="unit_id", how="inner")
        .join(properties.select("property_id", "submarket", "asset_class"),
              on="property_id", how="inner")
    )
    pay_lease = payments.join(
        leases.select("lease_id", "tenant_id"), on="lease_id", how="inner"
    )
    clause_stats = (
        clauses.with_columns(adverse=pl.col("clause_type").is_in(ADVERSE_CLAUSES))
        .group_by("lease_id")
        .agg(adverse_n=pl.col("adverse").sum(), clause_n=pl.len())
    )
    market = comp_market_stats(comps, as_of_months)

    rows = []
    for as_of in as_of_months:
        visible = pay_lease.filter(pl.col("due_date") <= as_of).with_columns(
            days_late=pl.when(pl.col("paid_date").is_null() | (pl.col("paid_date") > as_of))
            .then((pl.lit(as_of) - pl.col("due_date")).dt.total_days())
            .otherwise((pl.col("paid_date") - pl.col("due_date")).dt.total_days())
            .cast(pl.Float64),
            unpaid=(
                pl.col("paid_date").is_null() | (pl.col("paid_date") > as_of)
            ),
        )

        def window(months_back: int) -> pl.DataFrame:
            return visible.filter(pl.col("due_date") > _month_add(as_of, -months_back))

        w3 = window(3).group_by("tenant_id").agg(
            days_late_mean_3m=pl.col("days_late").mean())
        w6 = window(6).group_by("tenant_id").agg(
            days_late_mean_6m=pl.col("days_late").mean(),
            days_late_max_6m=pl.col("days_late").max(),
            late_share_6m=(pl.col("days_late") > 5).mean(),
        )
        w12 = window(12).group_by("tenant_id").agg(
            days_late_mean_12m=pl.col("days_late").mean())
        unpaid = visible.group_by("tenant_id").agg(unpaid_count=pl.col("unpaid").sum())

        # trend: slope of monthly mean days-late over the last 6 months
        # least-squares slope via covariance identity, pure Polars expressions
        x = pl.col("month_idx").cast(pl.Float64)
        y = pl.col("m_late")
        var_x = (x * x).mean() - x.mean() ** 2
        trend = (
            window(6)
            .with_columns(month_idx=(
                (pl.col("due_date").dt.year() - as_of.year) * 12
                + (pl.col("due_date").dt.month() - as_of.month)
            ))
            .group_by("tenant_id", "month_idx")
            .agg(m_late=pl.col("days_late").mean())
            .group_by("tenant_id")
            .agg(
                days_late_trend_6m=pl.when(pl.len() >= 2)
                .then(((x * y).mean() - x.mean() * y.mean()) / var_x)
                .otherwise(0.0)
            )
        )

        wo12 = (
            work_orders.filter(
                (pl.col("opened_at") <= as_of)
                & (pl.col("opened_at") > _month_add(as_of, -12))
            )
            .group_by("tenant_id")
            .agg(
                wo_count_12m=pl.len(),
                dispute_rate_12m=pl.col("dispute_flag").mean(),
            )
        )

        active = lease_meta.filter(
            (pl.col("commencement") <= as_of) & (pl.col("expiration") > as_of)
        )
        m_stats = market.filter(pl.col("as_of_month") == as_of)
        tenant_leases = (
            active.join(m_stats, on=["submarket", "asset_class"], how="left")
            .with_columns(
                monthly_due=pl.col("base_rent_psf") * pl.col("unit_rsf") / 12.0,
                rtm=pl.col("base_rent_psf") / pl.col("comp_median_rent_6m"),
            )
            .join(clause_stats, on="lease_id", how="left")
            .group_by("tenant_id")
            .agg(
                n_active_leases=pl.len(),
                total_monthly_due=pl.col("monthly_due").sum(),
                rent_to_market=(
                    (pl.col("rtm") * pl.col("unit_rsf")).sum() / pl.col("unit_rsf").sum()
                ),
                deposit_coverage_months=(
                    pl.col("security_deposit").sum()
                    / pl.col("monthly_due").sum().clip(lower_bound=1e-9)
                ),
                adverse_clause_share=(
                    pl.col("adverse_n").fill_null(0).sum()
                    / pl.col("clause_n").fill_null(0).sum().clip(lower_bound=1)
                ),
                tenure_months=(
                    (pl.lit(as_of) - pl.col("commencement").min()).dt.total_days() / 30.4
                ),
            )
        )

        feats = (
            tenant_leases.join(w3, on="tenant_id", how="left")
            .join(w6, on="tenant_id", how="left")
            .join(w12, on="tenant_id", how="left")
            .join(unpaid, on="tenant_id", how="left")
            .join(trend, on="tenant_id", how="left")
            .join(wo12, on="tenant_id", how="left")
            .join(
                tenants.select("tenant_id", "credit_rating", "industry_naics"),
                on="tenant_id", how="left",
            )
            .with_columns(
                credit_rating_ord=pl.col("credit_rating").replace_strict(
                    RATING_ORD, default=3).cast(pl.Float64),
                sector_distress_idx=pl.col("industry_naics").replace_strict(
                    {k: v[1] for k, v in NAICS_SECTORS.items()}, default=1.0
                ).cast(pl.Float64),
                as_of_month=pl.lit(as_of),
            )
            .drop("credit_rating", "industry_naics")
        )
        rows.append(feats)

    out = pl.concat(rows, how="diagonal")
    fill = {c: 0.0 for c in ["days_late_mean_3m", "days_late_mean_6m", "days_late_mean_12m",
                             "days_late_max_6m", "late_share_6m", "days_late_trend_6m",
                             "unpaid_count", "dispute_rate_12m", "wo_count_12m"]}
    return out.with_columns([pl.col(c).fill_null(v).cast(pl.Float64) for c, v in fill.items()])


def delinquency_events(payments: pl.DataFrame, leases: pl.DataFrame,
                       observed_through: date) -> pl.DataFrame:
    """First materially unpaid due date per lease (the 'default' event).

    A payment counts as a delinquency event only once it is 60+ days past due
    with nothing paid, judged against `observed_through` (no peeking past the
    end of the observation window).
    """
    return (
        payments.filter(
            (pl.col("amount_paid") <= 0)
            & pl.col("paid_date").is_null()
            & (pl.col("due_date") <= _month_add(observed_through, -2))
        )
        .join(leases.select("lease_id", "tenant_id"), on="lease_id", how="inner")
        .group_by("lease_id", "tenant_id")
        .agg(event_date=pl.col("due_date").min())
    )


def tenant_risk_labels(
    frames: dict[str, pl.DataFrame],
    as_of_months: list[date],
    observed_through: date,
    horizon_months: int = 6,
) -> pl.DataFrame:
    """Label: tenant has a delinquency event in (as_of, as_of + horizon]."""
    events = delinquency_events(frames["payments"], frames["leases"], observed_through)
    rows = []
    for as_of in as_of_months:
        horizon_end = _month_add(as_of, horizon_months)
        labeled = events.filter(
            (pl.col("event_date") > as_of) & (pl.col("event_date") <= horizon_end)
        ).select("tenant_id").unique().with_columns(label=pl.lit(1))
        rows.append(labeled.with_columns(as_of_month=pl.lit(as_of)))
    return pl.concat(rows)


# --------------------------------------------------------------------------
# lease pricing feature group
# --------------------------------------------------------------------------

def lease_pricing_features(
    frames: dict[str, pl.DataFrame], events: pl.DataFrame
) -> pl.DataFrame:
    """Features for pricing events.

    `events` columns: unit_id, event_date, term_months, lease_type
    (+ optional target column carried through untouched).
    """
    units, properties = frames["units"], frames["properties"]
    comps, leases = frames["market_comps"], frames["leases"]

    months = sorted({_month_floor(d) for d in events["event_date"].to_list()})
    market = comp_market_stats(comps, months)
    occupancy = building_occupancy(leases, units, months)

    return (
        events.with_columns(as_of_month=pl.col("event_date").dt.month_start())
        .join(units.select("unit_id", "property_id", "floor",
                           pl.col("rsf").alias("unit_rsf"),
                           pl.col("condition_grade").alias("unit_condition")),
              on="unit_id", how="inner")
        .join(properties.select("property_id", "submarket", "asset_class", "year_built",
                                pl.col("name").alias("property_name")),
              on="property_id", how="inner")
        .join(market, on=["submarket", "asset_class", "as_of_month"], how="left")
        .join(occupancy, on=["property_id", "as_of_month"], how="left")
        .with_columns(
            property_age=(pl.col("event_date").dt.year() - pl.col("year_built"))
            .cast(pl.Float64),
            condition_ord=pl.col("unit_condition").replace_strict(CONDITION_ORD, default=2)
            .cast(pl.Float64),
            asset_class_ord=pl.col("asset_class").replace_strict(ASSET_ORD, default=0)
            .cast(pl.Float64),
            lease_type_ord=pl.col("lease_type").replace_strict(LEASE_TYPE_ORD, default=0)
            .cast(pl.Float64),
            building_vacancy=(1.0 - pl.col("occupancy").fill_null(0.5)),
            floor=pl.col("floor").cast(pl.Float64),
            unit_rsf=pl.col("unit_rsf").cast(pl.Float64),
            term_months=pl.col("term_months").cast(pl.Float64),
            comp_count_6m=pl.col("comp_count_6m").fill_null(0).cast(pl.Float64),
        )
    )
