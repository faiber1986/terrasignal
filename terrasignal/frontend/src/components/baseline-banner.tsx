"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch, type Schemas } from "@/lib/api/client";
import { useLocale } from "@/lib/i18n";

type KillSwitchState = Schemas["KillSwitchState"];

/** Persistent banner whenever the kill switch is engaged. Every model number on
 * screen is then a labeled comp-median heuristic, not a model output (§8.6). */
export function BaselineBanner() {
  const { t } = useLocale();
  const { data } = useQuery({
    queryKey: ["kill-switch"],
    queryFn: () => apiFetch<KillSwitchState>("/governance/kill-switch"),
    refetchInterval: 15_000,
  });

  if (!data?.baseline_mode) return null;

  return (
    <div className="border-b border-band-amber/40 bg-band-amber/10 px-6 py-2 text-center text-sm font-medium text-band-amber">
      {t("banner.baseline")}
    </div>
  );
}
