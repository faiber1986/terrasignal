"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader, PageShell } from "@/components/page-shell";
import {
  BandBadge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorNote,
  Skeleton,
  Tag,
} from "@/components/ui/primitives";
import { apiFetch, ApiError, type Schemas } from "@/lib/api/client";
import { hasRole, useAuth } from "@/lib/auth";
import { shortDate } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type ModelVersionOut = Schemas["ModelVersionOut"];
type DriftMetricOut = Schemas["DriftMetricOut"];
type AuditEventOut = Schemas["AuditEventOut"];
type KillSwitchState = Schemas["KillSwitchState"];

const TAB_KEYS = ["killSwitch", "models", "drift", "audit"] as const;
type Tab = (typeof TAB_KEYS)[number];

export default function GovernancePage() {
  return (
    <PageShell>
      <Governance />
    </PageShell>
  );
}

function Governance() {
  const { t } = useLocale();
  const [tab, setTab] = useState<Tab>("killSwitch");
  const TAB_LABELS: Record<Tab, string> = {
    killSwitch: t("governance.tabKillSwitch"),
    models: t("governance.tabModels"),
    drift: t("governance.tabDrift"),
    audit: t("governance.tabAudit"),
  };
  return (
    <>
      <PageHeader title={t("governance.title")} subtitle={t("governance.subtitle")} />
      <div className="mb-4 flex gap-1 border-b border-surface-border">
        {TAB_KEYS.map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              tab === k
                ? "border-brand text-ink"
                : "border-transparent text-ink-muted hover:text-ink",
            )}
          >
            {TAB_LABELS[k]}
          </button>
        ))}
      </div>

      {tab === "killSwitch" && <KillSwitchPanel />}
      {tab === "models" && <ModelsPanel />}
      {tab === "drift" && <DriftPanel />}
      {tab === "audit" && <AuditPanel />}
    </>
  );
}

function KillSwitchPanel() {
  const { t } = useLocale();
  const { user } = useAuth();
  const qc = useQueryClient();
  const isAdmin = hasRole(user, "admin");

  const state = useQuery({
    queryKey: ["kill-switch"],
    queryFn: () => apiFetch<KillSwitchState>("/governance/kill-switch"),
  });

  const flip = useMutation({
    mutationFn: (baseline: boolean) =>
      apiFetch<KillSwitchState>("/governance/kill-switch", {
        method: "POST",
        body: {
          baseline_mode: baseline,
          reason: baseline ? "Manual kill-switch engage from console" : "Manual restore from console",
        },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kill-switch"] }),
  });

  const engaged = state.data?.baseline_mode ?? false;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("governance.killSwitchTitle")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="text-sm text-ink-muted">{t("governance.killSwitchBody")}</p>
        <div className="flex items-center gap-3">
          <span className="text-sm text-ink">{t("governance.currentState")}</span>
          {state.isLoading ? (
            <Skeleton className="h-6 w-24" />
          ) : engaged ? (
            <BandBadge band="amber" label={t("governance.baselinePaused")} />
          ) : (
            <BandBadge band="green" label={t("governance.liveServing")} />
          )}
        </div>

        {isAdmin ? (
          <Button
            variant={engaged ? "primary" : "danger"}
            disabled={flip.isPending || state.isLoading}
            onClick={() => flip.mutate(!engaged)}
          >
            {flip.isPending
              ? t("governance.applying")
              : engaged
                ? t("governance.restoreModels")
                : t("governance.engageKillSwitch")}
          </Button>
        ) : (
          <p className="text-sm text-ink-faint">{t("governance.adminOnly")}</p>
        )}
        {flip.error && (
          <ErrorNote>
            {flip.error instanceof ApiError ? flip.error.message : t("governance.errorFlip")}
          </ErrorNote>
        )}
      </CardBody>
    </Card>
  );
}

function ModelsPanel() {
  const { t, locale } = useLocale();
  const { user } = useAuth();
  const qc = useQueryClient();
  const isApprover = hasRole(user, "approver");

  const models = useQuery({
    queryKey: ["models-active"],
    queryFn: () => apiFetch<ModelVersionOut[]>("/models/active"),
  });

  const approve = useMutation({
    mutationFn: (m: ModelVersionOut) =>
      apiFetch(`/models/${m.model_name}/versions/${m.version}/approve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models-active"] }),
  });

  if (models.error) return <ErrorNote>{t("governance.errorRegistry")}</ErrorNote>;

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
          <tr>
            <th className="px-4 py-2 font-medium">{t("governance.colModel")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colVersion")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colStatus")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colMetrics")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colApproved")}</th>
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">
          {models.isLoading && (
            <tr>
              <td colSpan={6} className="px-4 py-3">
                <Skeleton className="h-5 w-full" />
              </td>
            </tr>
          )}
          {(models.data ?? []).map((m) => (
            <tr key={`${m.model_name}-${m.version}`}>
              <td className="px-4 py-2.5 font-medium text-ink">{m.model_name}</td>
              <td className="px-4 py-2.5 tnum">v{m.version}</td>
              <td className="px-4 py-2.5">
                <StatusTag status={m.status} />
              </td>
              <td className="px-4 py-2.5 text-xs text-ink-muted">
                {Object.entries(m.metrics)
                  .slice(0, 3)
                  .map(([k, v]) => `${k}: ${v.toFixed(3)}`)
                  .join(" · ")}
              </td>
              <td className="px-4 py-2.5 text-xs text-ink-muted">
                {m.approved_by ? `${m.approved_by} · ${shortDate(m.approved_at!, locale)}` : "—"}
              </td>
              <td className="px-4 py-2.5 text-right">
                {m.status === "PendingManualApproval" && isApprover && (
                  <Button size="sm" disabled={approve.isPending} onClick={() => approve.mutate(m)}>
                    {t("governance.approve")}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {approve.error && (
        <div className="p-3">
          <ErrorNote>
            {approve.error instanceof ApiError ? approve.error.message : t("governance.errorApprove")}
          </ErrorNote>
        </div>
      )}
    </Card>
  );
}

function DriftPanel() {
  const { t, locale } = useLocale();
  const drift = useQuery({
    queryKey: ["drift"],
    queryFn: () => apiFetch<DriftMetricOut[]>("/governance/drift"),
  });

  if (drift.error) return <ErrorNote>{t("governance.errorDrift")}</ErrorNote>;

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
          <tr>
            <th className="px-4 py-2 font-medium">{t("governance.colModel")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colFeature")}</th>
            <th className="px-4 py-2 text-right font-medium">{t("governance.colPsi")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colStatus")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colComputed")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">
          {drift.isLoading && (
            <tr>
              <td colSpan={5} className="px-4 py-3">
                <Skeleton className="h-5 w-full" />
              </td>
            </tr>
          )}
          {(drift.data ?? []).map((d, i) => (
            <tr key={`${d.model_name}-${d.feature_name}-${i}`}>
              <td className="px-4 py-2.5 text-ink-muted">{d.model_name}</td>
              <td className="px-4 py-2.5 text-ink">{d.feature_name}</td>
              <td className="px-4 py-2.5 text-right tnum">{d.psi.toFixed(3)}</td>
              <td className="px-4 py-2.5">
                <BandBadge band={d.status} label={d.status} />
              </td>
              <td className="px-4 py-2.5 text-xs tnum text-ink-faint">
                {shortDate(d.computed_at, locale)}
              </td>
            </tr>
          ))}
          {!drift.isLoading && (drift.data?.length ?? 0) === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-ink-faint">
                {t("governance.emptyDrift")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}

function AuditPanel() {
  const { t, locale } = useLocale();
  const audit = useQuery({
    queryKey: ["audit"],
    queryFn: () => apiFetch<AuditEventOut[]>("/governance/audit?limit=50"),
  });

  if (audit.error) {
    const forbidden = audit.error instanceof ApiError && audit.error.status === 403;
    return (
      <ErrorNote>
        {forbidden ? t("governance.errorAuditForbidden") : t("governance.errorAudit")}
      </ErrorNote>
    );
  }

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-border bg-surface-sunken text-left text-xs text-ink-muted">
          <tr>
            <th className="px-4 py-2 font-medium">{t("governance.colWhen")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colActor")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colEvent")}</th>
            <th className="px-4 py-2 font-medium">{t("governance.colEntity")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">
          {audit.isLoading && (
            <tr>
              <td colSpan={4} className="px-4 py-3">
                <Skeleton className="h-5 w-full" />
              </td>
            </tr>
          )}
          {(audit.data ?? []).map((e) => (
            <tr key={e.event_id}>
              <td className="px-4 py-2 text-xs tnum text-ink-faint">
                {shortDate(e.occurred_at, locale)}
              </td>
              <td className="px-4 py-2 text-ink-muted">
                {e.actor} <span className="text-ink-faint">· {e.actor_role}</span>
              </td>
              <td className="px-4 py-2">
                <Tag>{e.event_type}</Tag>
              </td>
              <td className="px-4 py-2 text-xs text-ink-muted">
                {e.entity_type}/{e.entity_id}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function StatusTag({ status }: { status: string }) {
  const tone =
    status === "Approved"
      ? "text-band-green"
      : status === "PendingManualApproval"
        ? "text-band-amber"
        : "text-ink-muted";
  return <Tag className={tone}>{status}</Tag>;
}
