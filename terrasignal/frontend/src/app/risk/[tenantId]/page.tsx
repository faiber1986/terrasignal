"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";

import { FeedbackActions } from "@/components/override-dialog";
import { PageHeader, PageShell } from "@/components/page-shell";
import { ShapDrivers } from "@/components/shap-drivers";
import {
  BandBadge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorNote,
  Skeleton,
  Tag,
} from "@/components/ui/primitives";
import { apiFetch, type Schemas } from "@/lib/api/client";
import { bandLabel, pct, rentPsf, shortDate, usd } from "@/lib/format";
import { useLocale } from "@/lib/i18n";

type TenantDetail = Schemas["TenantDetail"];
type RiskScoreResponse = Schemas["RiskScoreResponse"];

export default function TenantPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = use(params);
  return (
    <PageShell>
      <TenantDetailView tenantId={tenantId} />
    </PageShell>
  );
}

function TenantDetailView({ tenantId }: { tenantId: string }) {
  const { t, locale } = useLocale();
  const qc = useQueryClient();
  const key = ["tenant", tenantId];
  const { data, isLoading, error } = useQuery({
    queryKey: key,
    queryFn: () => apiFetch<TenantDetail>(`/risk/tenants/${tenantId}`),
  });

  const score = useMutation({
    mutationFn: () =>
      apiFetch<RiskScoreResponse>("/risk/score", { method: "POST", body: { tenant_id: tenantId } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ["risk-queue"] });
    },
  });

  if (error) {
    return <ErrorNote>{t("tenant.errorNotFound")}</ErrorNote>;
  }

  const latest = data?.latest ?? null;

  return (
    <>
      <div className="mb-2">
        <Link href="/risk" className="text-sm text-ink-muted hover:text-brand">
          {t("tenant.back")}
        </Link>
      </div>
      <PageHeader
        title={data?.name ?? tenantId}
        subtitle={data ? `${data.industry} · ${data.tenant_id}` : undefined}
        actions={
          <Button size="sm" onClick={() => score.mutate()} disabled={score.isPending}>
            {score.isPending ? t("tenant.scoring") : t("tenant.scoreNow")}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle>{t("tenant.defaultRisk")}</CardTitle>
            </CardHeader>
            <CardBody>
              {isLoading ? (
                <Skeleton className="h-16 w-full" />
              ) : latest ? (
                <>
                  <div className="flex items-baseline gap-3">
                    <span className="tnum text-3xl font-semibold text-ink">{pct(latest.pd)}</span>
                    <BandBadge band={latest.band} label={bandLabel(latest.band, t)} />
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">
                    {t("tenant.scoreMeta", {
                      version: latest.model_version,
                      source: latest.baseline_mode
                        ? t("tenant.sourceBaseline")
                        : t("tenant.sourceModel"),
                      date: shortDate(latest.as_of, locale),
                    })}
                  </p>
                  <div className="mt-4">
                    <p className="mb-2 text-xs font-medium text-ink-muted">{t("tenant.whyThisScore")}</p>
                    <ShapDrivers drivers={latest.drivers} />
                  </div>
                  <div className="mt-4 border-t border-surface-border pt-3">
                    <FeedbackActions predictionId={latest.prediction_id} invalidateKeys={[key]} />
                  </div>
                </>
              ) : (
                <p className="text-sm text-ink-muted">
                  {t("tenant.noScoreYet", { scoreNow: t("tenant.scoreNow") })}
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("tenant.tenantCard")}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-1 text-sm">
              <Row label={t("tenant.industry")} value={data?.industry} />
              <Row
                label={t("tenant.creditRating")}
                value={data?.credit_rating ?? t("tenant.notRated")}
              />
              <Row
                label={t("tenant.activeLeases")}
                value={data ? data.leases.length.toString() : undefined}
              />
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>{t("tenant.leases")}</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">{t("tenant.colLease")}</th>
                    <th className="px-4 py-2 font-medium">{t("tenant.colProperty")}</th>
                    <th className="px-4 py-2 text-right font-medium">{t("tenant.colBaseRent")}</th>
                    <th className="px-4 py-2 text-right font-medium">{t("tenant.colRsf")}</th>
                    <th className="px-4 py-2 font-medium">{t("tenant.colExpires")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {data?.leases.map((l) => (
                    <tr key={l.lease_id}>
                      <td className="px-4 py-2">
                        <span className="tnum">{l.lease_id}</span>
                        <div className="text-xs text-ink-faint">{l.lease_type}</div>
                      </td>
                      <td className="px-4 py-2 text-ink-muted">
                        {l.property_name}
                        <div className="text-xs text-ink-faint">{l.submarket}</div>
                      </td>
                      <td className="px-4 py-2 text-right tnum">{rentPsf(l.base_rent_psf)}</td>
                      <td className="px-4 py-2 text-right tnum">{l.unit_rsf.toLocaleString()}</td>
                      <td className="px-4 py-2 tnum text-ink-muted">{shortDate(l.expiration, locale)}</td>
                    </tr>
                  ))}
                  {isLoading && (
                    <tr>
                      <td colSpan={5} className="px-4 py-3">
                        <Skeleton className="h-5 w-full" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("tenant.recentPayments")}</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">{t("tenant.colDue")}</th>
                    <th className="px-4 py-2 font-medium">{t("tenant.colPaid")}</th>
                    <th className="px-4 py-2 text-right font-medium">{t("tenant.colAmountDue")}</th>
                    <th className="px-4 py-2 text-right font-medium">{t("tenant.colDaysLate")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {(data?.payment_history ?? []).slice(-10).reverse().map((p, i) => (
                    <tr key={`${p.lease_id}-${p.due_date}-${i}`}>
                      <td className="px-4 py-2 tnum text-ink-muted">{shortDate(p.due_date, locale)}</td>
                      <td className="px-4 py-2 tnum text-ink-muted">
                        {p.paid_date ? shortDate(p.paid_date, locale) : "—"}
                      </td>
                      <td className="px-4 py-2 text-right tnum">{usd(p.amount_due)}</td>
                      <td className="px-4 py-2 text-right">
                        {p.days_late == null ? (
                          <Tag>{t("common.unpaid")}</Tag>
                        ) : (
                          <span className={p.days_late > 5 ? "tnum text-band-red" : "tnum text-ink-muted"}>
                            {p.days_late}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-ink-muted">{label}</span>
      {value ? <span className="text-ink">{value}</span> : <Skeleton className="h-4 w-16" />}
    </div>
  );
}
