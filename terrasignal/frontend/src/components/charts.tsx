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

type ExpirationMonth = Schemas["ExpirationMonth"];

/** Risk-score distribution. Bars colored by the governed amber/red bands so the
 * tail (high-PD tenants) reads at a glance. */
export function RiskHistogram({ buckets }: { buckets: { lo: number; hi: number; count: number }[] }) {
  const data = buckets.map((b) => ({
    label: `${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`,
    count: b.count,
    color: b.lo >= 0.3 ? "#b91c1c" : b.lo >= 0.15 ? "#b45309" : "#0e7490",
  }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#94a3b8" }} interval={0} />
        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#94a3b8" }} />
        <Tooltip
          cursor={{ fill: "#f1f5f9" }}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(v: number) => [`${v} tenants`, "Count"]}
          labelFormatter={(l) => `PD ${l}`}
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
  const data = months.map((m) => ({
    label: monthLabel(m.month),
    rent: m.annual_rent_expiring,
    leases: m.leases_expiring,
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#94a3b8" }} interval={1} />
        <YAxis
          tick={{ fontSize: 10, fill: "#94a3b8" }}
          tickFormatter={(v: number) => usdCompact(v)}
          width={48}
        />
        <Tooltip
          cursor={{ fill: "#f1f5f9" }}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(v: number, name) =>
            name === "rent" ? [usdCompact(v), "Annual rent"] : [v, "Leases"]
          }
        />
        <Bar dataKey="rent" fill="#0e7490" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
