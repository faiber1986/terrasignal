/** Tiny inline SVG sparkline for days-late trend in the risk queue. No chart
 * library — it has to render fast in dozens of table rows. */
export function Sparkline({
  values,
  width = 96,
  height = 24,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  if (values.length < 2) {
    return <span className="text-xs text-ink-faint">—</span>;
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`)
    .join(" ");
  const last = values[values.length - 1] ?? 0;
  const rising = last > (values[0] ?? 0);

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke={rising ? "#b45309" : "#15803d"}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
