"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Sparkline } from "@/components/sparkline";
import { BandBadge, Card, ErrorNote, Skeleton, Tag } from "@/components/ui/primitives";
import { apiFetch, type Schemas } from "@/lib/api/client";
import { bandLabel, pct } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type RiskQueueItem = Schemas["RiskQueueItem"];
type SortKey = "pd" | "tenant_name" | "credit_rating";

export default function RiskQueuePage() {
  return (
    <PageShell>
      <RiskQueue />
    </PageShell>
  );
}

function RiskQueue() {
  const { t } = useLocale();
  const [sort, setSort] = useState<SortKey>("pd");
  const { data, isLoading, error } = useQuery({
    queryKey: ["risk-queue"],
    queryFn: () => apiFetch<RiskQueueItem[]>("/risk/queue?limit=100"),
  });

  const rows = [...(data ?? [])].sort((a, b) => {
    if (sort === "pd") return b.pd - a.pd;
    if (sort === "tenant_name") return a.tenant_name.localeCompare(b.tenant_name);
    return (a.credit_rating ?? "ZZ").localeCompare(b.credit_rating ?? "ZZ");
  });

  return (
    <>
      <PageHeader title={t("risk.title")} subtitle={t("risk.subtitle")} />

      {error && <ErrorNote>{t("risk.errorQueue")}</ErrorNote>}

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
            <tr>
              <Th onClick={() => setSort("tenant_name")} active={sort === "tenant_name"}>
                {t("risk.colTenant")}
              </Th>
              <Th>{t("risk.colIndustry")}</Th>
              <Th onClick={() => setSort("credit_rating")} active={sort === "credit_rating"}>
                {t("risk.colCredit")}
              </Th>
              <Th onClick={() => setSort("pd")} active={sort === "pd"} className="text-right">
                {t("risk.colPd")}
              </Th>
              <Th>{t("risk.colTopDriver")}</Th>
              <Th className="text-right">{t("risk.colTrend")}</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {isLoading &&
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td colSpan={6} className="px-4 py-3">
                    <Skeleton className="h-5 w-full" />
                  </td>
                </tr>
              ))}

            {rows.map((r) => (
              <tr key={r.tenant_id} className="hover:bg-surface-sunken">
                <td className="px-4 py-2.5">
                  <Link href={`/risk/${r.tenant_id}`} className="font-medium text-ink hover:text-brand">
                    {r.tenant_name}
                  </Link>
                  <div className="text-xs text-ink-faint">{r.tenant_id}</div>
                </td>
                <td className="px-4 py-2.5 text-ink-muted">{r.industry}</td>
                <td className="px-4 py-2.5">
                  <Tag>{r.credit_rating ?? t("risk.notRatedShort")}</Tag>
                </td>
                <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <span className="tnum font-semibold text-ink">{pct(r.pd)}</span>
                    <BandBadge band={r.band} label={bandLabel(r.band, t)} />
                  </div>
                </td>
                <td className="px-4 py-2.5 text-xs text-ink-muted">{r.top_driver}</td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end">
                    <Sparkline values={r.trend} />
                  </div>
                </td>
              </tr>
            ))}

            {!isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-ink-faint">
                  {t("risk.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function Th({
  children,
  onClick,
  active,
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  className?: string;
}) {
  return (
    <th
      className={cn("px-4 py-2.5 font-medium", onClick && "cursor-pointer select-none", className)}
      onClick={onClick}
      aria-sort={active ? "descending" : undefined}
    >
      <span className={cn(active && "text-ink")}>{children}</span>
      {active && <span className="ml-1 text-ink-faint">▼</span>}
    </th>
  );
}
