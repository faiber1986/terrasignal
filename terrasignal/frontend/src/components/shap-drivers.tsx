import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type ShapDriver = Schemas["ShapDriverOut"];

/** SHAP driver bars — always shown next to the number they explain (§8.3).
 * Bars are scaled to the largest absolute contribution in the set; red pushes
 * the prediction up (more risk / higher rent), blue pulls it down. */
export function ShapDrivers({ drivers }: { drivers: ShapDriver[] }) {
  if (drivers.length === 0) {
    return <p className="text-sm text-ink-faint">No driver attribution available.</p>;
  }
  const max = Math.max(...drivers.map((d) => Math.abs(d.shap))) || 1;

  return (
    <ul className="space-y-2">
      {drivers.map((d) => {
        const widthPct = (Math.abs(d.shap) / max) * 100;
        const positive = d.shap >= 0;
        return (
          <li key={d.feature} className="grid grid-cols-[1fr_auto] items-center gap-x-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="truncate text-ink" title={d.label}>
                {d.label}
              </span>
              <span className="tnum text-ink-faint">{formatValue(d.value)}</span>
            </div>
            <span className="tnum text-ink-muted">{positive ? "+" : "−"}{Math.abs(d.shap).toFixed(3)}</span>
            <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-surface-sunken">
              <div
                className={cn("h-full rounded-full", positive ? "bg-band-red" : "bg-brand")}
                style={{ width: `${widthPct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function formatValue(v: number): string {
  if (Number.isInteger(v)) return v.toString();
  return v.toFixed(2);
}
