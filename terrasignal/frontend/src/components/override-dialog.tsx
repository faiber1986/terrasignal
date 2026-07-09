"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, ErrorNote, Label } from "@/components/ui/primitives";
import { apiFetch, ApiError, type Schemas } from "@/lib/api/client";
import { useLocale } from "@/lib/i18n";

type FeedbackResponse = Schemas["FeedbackResponse"];
type FeedbackRequest = Schemas["FeedbackRequest"];

// Mirrors the server-side allowlist in feedback.py — the server re-validates.
const REASON_CODE_VALUES = [
  "market_knowledge",
  "tenant_relationship",
  "data_quality_concern",
  "strategic_decision",
  "model_distrust",
  "other",
] as const;

const REASON_LABEL_KEYS: Record<(typeof REASON_CODE_VALUES)[number], string> = {
  market_knowledge: "feedback.reasonMarket",
  tenant_relationship: "feedback.reasonRelationship",
  data_quality_concern: "feedback.reasonDataQuality",
  strategic_decision: "feedback.reasonStrategic",
  model_distrust: "feedback.reasonDistrust",
  other: "feedback.reasonOther",
};

/** Accept / override-with-reason. Overrides require a structured reason code +
 * free text; both actions write to feedback + audit (§8.3). On success the
 * caller's queries are invalidated so lineage/feedback refresh. */
export function FeedbackActions({
  predictionId,
  invalidateKeys = [],
  overrideValue,
}: {
  predictionId: string;
  invalidateKeys?: unknown[][];
  overrideValue?: Record<string, unknown>;
}) {
  const { t } = useLocale();
  const qc = useQueryClient();
  const [mode, setMode] = useState<"idle" | "override">("idle");
  const [reasonCode, setReasonCode] = useState<(typeof REASON_CODE_VALUES)[number]>(
    REASON_CODE_VALUES[0],
  );
  const [comment, setComment] = useState("");
  const [done, setDone] = useState<"accept" | "override" | null>(null);

  const mutation = useMutation({
    mutationFn: (body: FeedbackRequest) =>
      apiFetch<FeedbackResponse>("/feedback", { method: "POST", body }),
    onSuccess: (_res, body) => {
      setDone(body.action);
      setMode("idle");
      invalidateKeys.forEach((key) => qc.invalidateQueries({ queryKey: key }));
    },
  });

  if (done) {
    return (
      <p className="text-sm text-band-green">
        {done === "accept" ? t("feedback.recordedAccept") : t("feedback.recordedOverride")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {mode === "idle" ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => mutation.mutate({ prediction_id: predictionId, action: "accept" })}
            disabled={mutation.isPending}
          >
            {t("feedback.accept")}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setMode("override")}>
            {t("feedback.override")}
          </Button>
        </div>
      ) : (
        <div className="space-y-2 rounded-md border border-surface-border bg-surface-sunken p-3">
          <div>
            <Label htmlFor="reason">{t("feedback.reasonCodeLabel")}</Label>
            <select
              id="reason"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value as (typeof REASON_CODE_VALUES)[number])}
              className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm"
            >
              {REASON_CODE_VALUES.map((value) => (
                <option key={value} value={value}>
                  {t(REASON_LABEL_KEYS[value])}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="comment">{t("feedback.commentLabel")}</Label>
            <textarea
              id="comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm"
              placeholder={t("feedback.commentPlaceholder")}
            />
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="danger"
              disabled={mutation.isPending}
              onClick={() =>
                mutation.mutate({
                  prediction_id: predictionId,
                  action: "override",
                  reason_code: reasonCode,
                  comment: comment || null,
                  override_value: overrideValue ?? null,
                })
              }
            >
              {t("feedback.submitOverride")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("idle")}>
              {t("feedback.cancel")}
            </Button>
          </div>
        </div>
      )}
      {mutation.error && (
        <ErrorNote>
          {mutation.error instanceof ApiError ? mutation.error.message : t("feedback.errorGeneric")}
        </ErrorNote>
      )}
    </div>
  );
}
