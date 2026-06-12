"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, ErrorNote, Label } from "@/components/ui/primitives";
import { apiFetch, ApiError, type Schemas } from "@/lib/api/client";

type FeedbackResponse = Schemas["FeedbackResponse"];
type FeedbackRequest = Schemas["FeedbackRequest"];

// Mirrors the server-side allowlist in feedback.py — the server re-validates.
const REASON_CODES: { value: string; label: string }[] = [
  { value: "market_knowledge", label: "Market knowledge" },
  { value: "tenant_relationship", label: "Tenant relationship" },
  { value: "data_quality_concern", label: "Data quality concern" },
  { value: "strategic_decision", label: "Strategic decision" },
  { value: "model_distrust", label: "Model distrust" },
  { value: "other", label: "Other" },
];

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
  const qc = useQueryClient();
  const [mode, setMode] = useState<"idle" | "override">("idle");
  const [reasonCode, setReasonCode] = useState(REASON_CODES[0]!.value);
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
        Recorded {done === "accept" ? "acceptance" : "override"} — written to the audit trail.
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
            Accept
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setMode("override")}>
            Override…
          </Button>
        </div>
      ) : (
        <div className="space-y-2 rounded-md border border-surface-border bg-surface-sunken p-3">
          <div>
            <Label htmlFor="reason">Reason code (required)</Label>
            <select
              id="reason"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
              className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm"
            >
              {REASON_CODES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="comment">Comment</Label>
            <textarea
              id="comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm"
              placeholder="What does the model miss here?"
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
              Submit override
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("idle")}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {mutation.error && (
        <ErrorNote>
          {mutation.error instanceof ApiError ? mutation.error.message : "Failed to record feedback"}
        </ErrorNote>
      )}
    </div>
  );
}
