"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { FanChart } from "@/components/fan-chart";
import { FeedbackActions } from "@/components/override-dialog";
import { PageHeader, PageShell } from "@/components/page-shell";
import { ShapDrivers } from "@/components/shap-drivers";
import {
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
import { pct, rentPsf, shortDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type RentQueueItem = Schemas["RentQueueItem"];
type RentForecastResponse = Schemas["RentForecastResponse"];
type RationaleResponse = Schemas["RationaleResponse"];

export default function PricingPage() {
  return (
    <PageShell>
      <PricingWorkbench />
    </PageShell>
  );
}

function PricingWorkbench() {
  const [selected, setSelected] = useState<string | null>(null);

  const queue = useQuery({
    queryKey: ["rent-queue"],
    queryFn: () => apiFetch<RentQueueItem[]>("/forecasts/queue?limit=100"),
  });

  const forecast = useQuery({
    queryKey: ["forecast", selected],
    queryFn: () =>
      apiFetch<RentForecastResponse>("/forecasts/rent", {
        method: "POST",
        body: { unit_id: selected },
      }),
    enabled: selected !== null,
  });

  return (
    <>
      <PageHeader
        title="Lease Pricing"
        subtitle="Renewal rent forecast with comps, drivers, and a grounded rationale memo"
      />

      {queue.error && <ErrorNote>Could not load the renewal queue — seed + score first.</ErrorNote>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
        {/* Unit picker */}
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle>Upcoming renewals</CardTitle>
          </CardHeader>
          <ul className="max-h-[36rem] divide-y divide-surface-border overflow-y-auto">
            {queue.isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <li key={i} className="px-4 py-3">
                  <Skeleton className="h-5 w-full" />
                </li>
              ))}
            {(queue.data ?? []).map((u) => (
              <li key={u.unit_id}>
                <button
                  onClick={() => setSelected(u.unit_id)}
                  className={cn(
                    "w-full px-4 py-3 text-left hover:bg-surface-sunken",
                    selected === u.unit_id && "bg-surface-sunken",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-ink">{u.property_name}</span>
                    <UpsidePill pct={u.upside_pct} />
                  </div>
                  <div className="mt-0.5 text-xs text-ink-faint">
                    {u.unit_id} · {u.submarket} · exp {shortDate(u.lease_expiration)}
                  </div>
                </button>
              </li>
            ))}
            {!queue.isLoading && (queue.data?.length ?? 0) === 0 && (
              <li className="px-4 py-8 text-center text-sm text-ink-faint">No renewals queued.</li>
            )}
          </ul>
        </Card>

        {/* Workbench */}
        <div className="space-y-4">
          {selected === null ? (
            <Card>
              <CardBody className="py-16 text-center text-sm text-ink-faint">
                Select a unit to forecast its renewal rent.
              </CardBody>
            </Card>
          ) : forecast.isLoading ? (
            <Card>
              <CardBody>
                <Skeleton className="h-40 w-full" />
              </CardBody>
            </Card>
          ) : forecast.error ? (
            <ErrorNote>This unit has no active lease to renew.</ErrorNote>
          ) : forecast.data ? (
            <ForecastDetail data={forecast.data} />
          ) : null}
        </div>
      </div>
    </>
  );
}

function ForecastDetail({ data }: { data: RentForecastResponse }) {
  const upside = data.current_rent_psf ? data.p50 / data.current_rent_psf - 1 : 0;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>
            {data.property_name} · {data.unit_id}
          </CardTitle>
        </CardHeader>
        <CardBody>
          <div className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <Metric label="p50 renewal" value={rentPsf(data.p50)} emphasize />
            <Metric label="in-place" value={rentPsf(data.current_rent_psf)} />
            <Metric label="upside" value={pct(upside)} tone={upside >= 0 ? "up" : "down"} />
            <Metric label="submarket comp (6m)" value={rentPsf(data.comp_median_rent_6m)} />
          </div>
          <FanChart
            p10={data.p10}
            p50={data.p50}
            p90={data.p90}
            current={data.current_rent_psf}
          />
          <p className="mt-3 text-xs text-ink-faint">
            {data.asset_class} · {data.submarket} · {data.unit_rsf.toLocaleString()} RSF · model v
            {data.model_version}
            {data.baseline_mode && " · baseline heuristic"}
          </p>
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>What drives the estimate</CardTitle>
          </CardHeader>
          <CardBody>
            <ShapDrivers drivers={data.drivers} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Nearest comps</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            <table className="w-full text-xs">
              <thead className="border-b border-surface-border bg-surface-sunken text-left text-ink-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Signed</th>
                  <th className="px-3 py-2 text-right font-medium">Rent</th>
                  <th className="px-3 py-2 text-right font-medium">Term</th>
                  <th className="px-3 py-2 text-right font-medium">TI</th>
                  <th className="px-3 py-2 text-right font-medium">Free</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {data.comps.map((c) => (
                  <tr key={c.comp_id}>
                    <td className="px-3 py-1.5 tnum text-ink-muted">{shortDate(c.signed_date)}</td>
                    <td className="px-3 py-1.5 text-right tnum">{rentPsf(c.rent_psf)}</td>
                    <td className="px-3 py-1.5 text-right tnum">{c.term_months}mo</td>
                    <td className="px-3 py-1.5 text-right tnum">${c.ti_allowance_psf.toFixed(0)}</td>
                    <td className="px-3 py-1.5 text-right tnum">{c.free_rent_months}mo</td>
                  </tr>
                ))}
                {data.comps.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-4 text-center text-ink-faint">
                      Thin submarket — no recent comps.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </CardBody>
        </Card>
      </div>

      <RationaleCard predictionId={data.prediction_id} />

      <Card>
        <CardHeader>
          <CardTitle>Pricing decision</CardTitle>
        </CardHeader>
        <CardBody>
          <FeedbackActions
            predictionId={data.prediction_id}
            invalidateKeys={[["forecast", data.unit_id]]}
            overrideValue={{ p50: data.p50 }}
          />
        </CardBody>
      </Card>
    </>
  );
}

function RationaleCard({ predictionId }: { predictionId: string }) {
  const memo = useMutation({
    mutationFn: () =>
      apiFetch<RationaleResponse>(`/forecasts/${predictionId}/rationale`, { method: "POST" }),
  });

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Rationale memo</CardTitle>
        <Button size="sm" variant="secondary" onClick={() => memo.mutate()} disabled={memo.isPending}>
          {memo.isPending ? "Generating…" : memo.data ? "Regenerate" : "Generate memo"}
        </Button>
      </CardHeader>
      <CardBody>
        {memo.data ? (
          <>
            <div className="mb-2 flex items-center gap-2">
              <Tag>{memo.data.label}</Tag>
              <Tag>{memo.data.backend}</Tag>
              <Tag className={memo.data.guard_passed ? "text-band-green" : "text-band-red"}>
                numeric guard {memo.data.guard_passed ? "passed" : "failed"}
              </Tag>
              {memo.data.fallback_used && <Tag>template fallback</Tag>}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{memo.data.memo}</p>
          </>
        ) : (
          <p className="text-sm text-ink-faint">
            Generate a grounded narrative — the model verbalizes the numbers above; a post-check
            rejects any figure not present in the forecast payload.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function Metric({
  label,
  value,
  emphasize,
  tone = "neutral",
}: {
  label: string;
  value: string;
  emphasize?: boolean;
  tone?: "neutral" | "up" | "down";
}) {
  const color = tone === "up" ? "text-band-green" : tone === "down" ? "text-band-red" : "text-ink";
  return (
    <div>
      <p className="text-xs text-ink-faint">{label}</p>
      <p className={cn("tnum font-semibold", emphasize ? "text-2xl" : "text-lg", color)}>{value}</p>
    </div>
  );
}

function UpsidePill({ pct: value }: { pct: number }) {
  const positive = value >= 0;
  return (
    <span
      className={cn(
        "tnum rounded px-1.5 py-0.5 text-xs font-medium",
        positive ? "bg-band-green/10 text-band-green" : "bg-band-red/10 text-band-red",
      )}
    >
      {positive ? "+" : ""}
      {pct(value)}
    </span>
  );
}
