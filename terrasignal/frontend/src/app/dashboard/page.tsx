"use client";

import { useQuery } from "@tanstack/react-query";

import { ExpirationWall, RiskHistogram } from "@/components/charts";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Card, CardBody, CardHeader, CardTitle, ErrorNote, Skeleton } from "@/components/ui/primitives";
import { apiFetch, ApiError, type Schemas } from "@/lib/api/client";
import { pct, shortDate, usdCompact } from "@/lib/format";
import { useLocale } from "@/lib/i18n";

type PortfolioSummary = Schemas["PortfolioSummary"];

export default function DashboardPage() {
  return (
    <PageShell>
      <Dashboard />
    </PageShell>
  );
}

function Dashboard() {
  const { t, locale } = useLocale();
  const { data, isLoading, error } = useQuery({
    queryKey: ["portfolio-summary"],
    queryFn: () => apiFetch<PortfolioSummary>("/portfolio/summary"),
  });

  return (
    <>
      <PageHeader
        title={t("dashboard.title")}
        subtitle={
          data
            ? t("dashboard.subtitle", {
                date: shortDate(data.as_of, locale),
                count: data.n_properties,
              })
            : undefined
        }
      />

      {error && <ErrorNote>{describe(error, t)}</ErrorNote>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi
          label={t("dashboard.noiAtRisk")}
          value={data ? usdCompact(data.noi_at_risk_annual) : undefined}
          hint={t("dashboard.noiAtRiskHint")}
          tone="risk"
        />
        <Kpi
          label={t("dashboard.watchlistTenants")}
          value={data ? data.watchlist_count.toString() : undefined}
          hint={data ? t("dashboard.watchlistHint", { pct: pct(data.avg_pd) }) : undefined}
          tone="risk"
        />
        <Kpi
          label={t("dashboard.renewalUpside")}
          value={data ? usdCompact(data.renewal_upside_annual) : undefined}
          hint={t("dashboard.renewalUpsideHint")}
          tone="up"
        />
        <Kpi
          label={t("dashboard.activeLeases")}
          value={data ? data.active_leases.toLocaleString() : undefined}
          hint={
            data
              ? t("dashboard.activeLeasesHint", { rsf: (data.total_rsf / 1_000_000).toFixed(1) })
              : undefined
          }
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.riskDistribution")}</CardTitle>
          </CardHeader>
          <CardBody>
            {data ? (
              <RiskHistogram buckets={data.risk_histogram as { lo: number; hi: number; count: number }[]} />
            ) : (
              <Skeleton className="h-[180px] w-full" />
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.expirationWall")}</CardTitle>
          </CardHeader>
          <CardBody>
            {data ? (
              <ExpirationWall months={data.expiration_wall} />
            ) : (
              <Skeleton className="h-[200px] w-full" />
            )}
          </CardBody>
        </Card>
      </div>

      {isLoading && <p className="mt-4 text-sm text-ink-faint">{t("dashboard.loadingPortfolio")}</p>}
    </>
  );
}

function Kpi({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value?: string;
  hint?: string;
  tone?: "neutral" | "risk" | "up";
}) {
  const valueColor =
    tone === "risk" ? "text-band-red" : tone === "up" ? "text-band-green" : "text-ink";
  return (
    <Card>
      <CardBody>
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</p>
        {value ? (
          <p className={`mt-1 text-2xl font-semibold tnum ${valueColor}`}>{value}</p>
        ) : (
          <Skeleton className="mt-2 h-7 w-24" />
        )}
        {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
      </CardBody>
    </Card>
  );
}

function describe(error: unknown, t: (key: string) => string): string {
  if (error instanceof ApiError) {
    if (error.status === 404 || error.status === 500) {
      return t("dashboard.errorNoData");
    }
    return error.message;
  }
  return t("dashboard.errorGeneric");
}
