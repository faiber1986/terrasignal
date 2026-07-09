"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Schemas } from "@/lib/api/client";
import { monthLabel, usdCompact } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

type ExpirationMonth = Schemas["ExpirationMonth"];

const AXIS_TICK = { light: "#94a3b8", dark: "#64748b" };
const CURSOR_FILL = { light: "#f1f5f9", dark: "#334155" };
const BAND_COLOR = {
  light: { low: "#0e7490", mid: "#b45309", high: "#b91c1c" },
  dark: { low: "#22b8d1", mid: "#f59e0b", high: "#ef4444" },
};
const BRAND_BAR = { light: "#0e7490", dark: "#22b8d1" };

/** Risk-score distribution. Bars colored by the governed amber/red bands so the
 * tail (high-PD tenants) reads at a glance. */
export function RiskHistogram({ buckets }: { buckets: { lo: number; hi: number; count: number }[] }) {
  const { t } = useLocale();
  const { theme } = useTheme();
  const band = BAND_COLOR[theme];
  const data = buckets.map((b) => ({
    label: `${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`,
    count: b.count,
    color: b.lo >= 0.3 ? band.high : b.lo >= 0.15 ? band.mid : band.low,
  }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: AXIS_TICK[theme] }} interval={0} />
        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: AXIS_TICK[theme] }} />
        <Tooltip
          cursor={{ fill: CURSOR_FILL[theme] }}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(v: number) => [`${v} ${t("charts.tenantsUnit")}`, t("charts.countLabel")]}
          labelFormatter={(l) => t("charts.pdLabel", { label: l })}
        />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {data.map((d) => (
            <Cell key={d.label} fill={d.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 18-month expiration wall: annual rent rolling off each month. */
export function ExpirationWall({ months }: { months: ExpirationMonth[] }) {
  const { t, locale } = useLocale();
  const { theme } = useTheme();
  const data = months.map((m) => ({
    label: monthLabel(m.month, locale),
    rent: m.annual_rent_expiring,
    leases: m.leases_expiring,
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: AXIS_TICK[theme] }} interval={1} />
        <YAxis
          tick={{ fontSize: 10, fill: AXIS_TICK[theme] }}
          tickFormatter={(v: number) => usdCompact(v)}
          width={48}
        />
        <Tooltip
          cursor={{ fill: CURSOR_FILL[theme] }}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(v: number, name) =>
            name === "rent" ? [usdCompact(v), t("charts.annualRent")] : [v, t("charts.leases")]
          }
        />
        <Bar dataKey="rent" fill={BRAND_BAR[theme]} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
