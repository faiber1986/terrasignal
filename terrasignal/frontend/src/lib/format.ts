/** Presentation-only formatters. All numbers shown in the UI are computed and
 * handed over by the backend (the engine owns the math); these only render. */

const USD0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const USD2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function usd(value: number): string {
  return USD0.format(value);
}

export function usd2(value: number): string {
  return USD2.format(value);
}

/** Compact dollars: $1.2M, $840K. For KPI tiles where space is tight. */
export function usdCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${Math.round(value / 1_000)}K`;
  return usd(value);
}

export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function rentPsf(value: number): string {
  return `${usd2(value)}/SF`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function monthLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export type Band = "green" | "amber" | "red";

export function bandLabel(band: Band): string {
  return { green: "Low", amber: "Watch", red: "High" }[band];
}
