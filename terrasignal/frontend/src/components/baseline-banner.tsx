"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch, type Schemas } from "@/lib/api/client";

type KillSwitchState = Schemas["KillSwitchState"];

/** Persistent banner whenever the kill switch is engaged. Every model number on
 * screen is then a labeled comp-median heuristic, not a model output (§8.6). */
export function BaselineBanner() {
  const { data } = useQuery({
    queryKey: ["kill-switch"],
    queryFn: () => apiFetch<KillSwitchState>("/governance/kill-switch"),
    refetchInterval: 15_000,
  });

  if (!data?.baseline_mode) return null;

  return (
    <div className="border-b border-band-amber/40 bg-band-amber/10 px-6 py-2 text-center text-sm font-medium text-band-amber">
      Baseline mode is engaged — models are paused. All scores and forecasts shown are
      comp-median heuristics, not model outputs.
    </div>
  );
}
