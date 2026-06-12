import { rentPsf } from "@/lib/format";

/** Horizontal range plot: the p10–p90 forecast band with the p50 estimate and
 * the in-place rent marked. A "fan" at a single renewal horizon. */
export function FanChart({
  p10,
  p50,
  p90,
  current,
}: {
  p10: number;
  p50: number;
  p90: number;
  current: number;
}) {
  const lo = Math.min(p10, current);
  const hi = Math.max(p90, current);
  const pad = (hi - lo) * 0.12 || 1;
  const min = lo - pad;
  const max = hi + pad;
  const x = (v: number) => ((v - min) / (max - min)) * 100;

  return (
    <div className="space-y-2">
      <div className="relative h-12">
        {/* axis */}
        <div className="absolute top-6 h-px w-full bg-surface-border" />
        {/* p10–p90 band */}
        <div
          className="absolute top-4 h-4 rounded bg-brand/15"
          style={{ left: `${x(p10)}%`, width: `${x(p90) - x(p10)}%` }}
        />
        {/* p50 marker */}
        <Marker pos={x(p50)} color="#0e7490" label="p50" labelText={rentPsf(p50)} emphasize />
        {/* current rent marker */}
        <Marker pos={x(current)} color="#475569" label="in-place" labelText={rentPsf(current)} below />
      </div>
      <div className="flex justify-between text-[11px] tnum text-ink-faint">
        <span>{rentPsf(p10)} (p10)</span>
        <span>{rentPsf(p90)} (p90)</span>
      </div>
    </div>
  );
}

function Marker({
  pos,
  color,
  label,
  labelText,
  emphasize = false,
  below = false,
}: {
  pos: number;
  color: string;
  label: string;
  labelText: string;
  emphasize?: boolean;
  below?: boolean;
}) {
  return (
    <div
      className="absolute flex -translate-x-1/2 flex-col items-center"
      style={{ left: `${pos}%`, top: below ? "1.75rem" : "-0.1rem" }}
    >
      {!below && (
        <span className="whitespace-nowrap text-[10px] font-medium" style={{ color }}>
          {label} {labelText}
        </span>
      )}
      <span
        className="my-0.5 h-4 w-0.5"
        style={{ backgroundColor: color, height: emphasize ? "1.25rem" : "1rem" }}
      />
      {below && (
        <span className="whitespace-nowrap text-[10px]" style={{ color }}>
          {label} {labelText}
        </span>
      )}
    </div>
  );
}
