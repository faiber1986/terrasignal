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
    return <ErrorNote>Tenant not found, or the backend isn’t seeded.</ErrorNote>;
  }

  const latest = data?.latest ?? null;

  return (
    <>
      <div className="mb-2">
        <Link href="/risk" className="text-sm text-ink-muted hover:text-brand">
          ← Risk Queue
        </Link>
      </div>
      <PageHeader
        title={data?.name ?? tenantId}
        subtitle={data ? `${data.industry} · ${data.tenant_id}` : undefined}
        actions={
          <Button size="sm" onClick={() => score.mutate()} disabled={score.isPending}>
            {score.isPending ? "Scoring…" : "Score now"}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle>Default risk</CardTitle>
            </CardHeader>
            <CardBody>
              {isLoading ? (
                <Skeleton className="h-16 w-full" />
              ) : latest ? (
                <>
                  <div className="flex items-baseline gap-3">
                    <span className="tnum text-3xl font-semibold text-ink">{pct(latest.pd)}</span>
                    <BandBadge band={latest.band} label={bandLabel(latest.band)} />
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">
                    Calibrated PD within 6 months · model v{latest.model_version} ·{" "}
                    {latest.baseline_mode ? "baseline heuristic" : "model"} · as of{" "}
                    {shortDate(latest.as_of)}
                  </p>
                  <div className="mt-4">
                    <p className="mb-2 text-xs font-medium text-ink-muted">Why this score</p>
                    <ShapDrivers drivers={latest.drivers} />
                  </div>
                  <div className="mt-4 border-t border-surface-border pt-3">
                    <FeedbackActions predictionId={latest.prediction_id} invalidateKeys={[key]} />
                  </div>
                </>
              ) : (
                <p className="text-sm text-ink-muted">
                  No score yet. Use <span className="font-medium">Score now</span> to generate one.
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Tenant</CardTitle>
            </CardHeader>
            <CardBody className="space-y-1 text-sm">
              <Row label="Industry" value={data?.industry} />
              <Row label="Credit rating" value={data?.credit_rating ?? "Not rated"} />
              <Row label="Active leases" value={data ? data.leases.length.toString() : undefined} />
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Leases</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Lease</th>
                    <th className="px-4 py-2 font-medium">Property</th>
                    <th className="px-4 py-2 text-right font-medium">Base rent</th>
                    <th className="px-4 py-2 text-right font-medium">RSF</th>
                    <th className="px-4 py-2 font-medium">Expires</th>
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
                      <td className="px-4 py-2 tnum text-ink-muted">{shortDate(l.expiration)}</td>
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
              <CardTitle>Recent payments</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Due</th>
                    <th className="px-4 py-2 font-medium">Paid</th>
                    <th className="px-4 py-2 text-right font-medium">Amount due</th>
                    <th className="px-4 py-2 text-right font-medium">Days late</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {(data?.payment_history ?? []).slice(-10).reverse().map((p, i) => (
                    <tr key={`${p.lease_id}-${p.due_date}-${i}`}>
                      <td className="px-4 py-2 tnum text-ink-muted">{shortDate(p.due_date)}</td>
                      <td className="px-4 py-2 tnum text-ink-muted">
                        {p.paid_date ? shortDate(p.paid_date) : "—"}
                      </td>
                      <td className="px-4 py-2 text-right tnum">{usd(p.amount_due)}</td>
                      <td className="px-4 py-2 text-right">
                        {p.days_late == null ? (
                          <Tag>unpaid</Tag>
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
