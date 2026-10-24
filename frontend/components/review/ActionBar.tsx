"use client";

import { CheckCircle2, FileCheck2, Loader2, RefreshCw, Send, Undo2, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { post } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Review } from "@/lib/types";

import { ErrorState, Modal, Tip } from "../ui";

const EDITABLE = new Set(["draft", "changes_requested"]);

export function ActionBar({ review, onChanged, onRechecked }: { review: Review; onChanged: () => void; onRechecked: () => void }) {
  const { user, can } = useSession();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"approve" | "request_changes" | null>(null);
  const [comment, setComment] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const { submission, gate, pending_edits: pendingEdits, revision } = review;
  const isAuthor = can("submit_content") && (user?.role !== "creator" || submission.author.id === user?.id);
  const editable = EDITABLE.has(submission.state);
  const reviewing = revision.review_status === "pending";
  const blocking = review.findings.filter((f) => gate.blocking.includes(f.id));

  async function act(name: string, fn: () => Promise<unknown>, after: () => void = onChanged) {
    setBusy(name);
    setError(null);
    try {
      await fn();
      setDialog(null);
      after();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  const transition = (action: string, body: Record<string, unknown> = {}) => act(action, () => post(`/api/reviews/${submission.id}/transition`, { action, ...body }));

  return (
    <div className="space-y-2" data-tour="actions">
      <div className="flex flex-wrap items-center gap-2">
        {isAuthor && editable && (
          <>
            <Tip text={pendingEdits ? `Creates revision ${revision.number + 1} with your ${pendingEdits} accepted or edited change(s) and checks it again.` : "Checks the current text again. Accept or edit suggestions first to apply them."}>
              <button type="button" className="btn-ghost" disabled={reviewing || busy !== null} onClick={() => act("recheck", () => post(`/api/reviews/${submission.id}/revisions`, { use_draft: true }), onRechecked)}>
                {busy === "recheck" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
                Re-check{pendingEdits ? ` with ${pendingEdits} change${pendingEdits > 1 ? "s" : ""}` : ""}
              </button>
            </Tip>
            <Tip text={gate.can_submit ? "Send to an approver. You can still see it change state here." : gate.message}>
              <button type="button" className="btn-teal" disabled={!gate.can_submit || reviewing || busy !== null} onClick={() => transition("submit")}>
                {busy === "submit" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" aria-hidden="true" />} Submit for approval
              </button>
            </Tip>
          </>
        )}
        {can("approve") && submission.state === "in_review" && (
          <>
            <button type="button" className="btn-teal" disabled={busy !== null} onClick={() => setDialog("approve")}>
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> Approve
            </button>
            <button type="button" className="btn-ghost" disabled={busy !== null} onClick={() => setDialog("request_changes")}>
              <Undo2 className="h-4 w-4" aria-hidden="true" /> Request changes
            </button>
          </>
        )}
        {can("approve") && submission.state === "approved" && (
          <button type="button" className="btn-ghost" disabled={busy !== null} onClick={() => transition("publish")}>
            <Upload className="h-4 w-4" aria-hidden="true" /> Mark as published
          </button>
        )}
        {(submission.state === "approved" || submission.state === "published") && (
          <Link href={`/receipt/${submission.id}`} className="btn-primary">
            <FileCheck2 className="h-4 w-4" aria-hidden="true" /> View Review Receipt
          </Link>
        )}
        {submission.state === "in_review" && !can("approve") && (
          <p className="text-sm text-navy-500">Waiting for an approver. Switch to abhi4 (Approver) in the top right to approve it.</p>
        )}
      </div>
      {!gate.can_submit && isAuthor && editable && !reviewing && <p className="text-xs text-navy-500">{gate.message}</p>}
      {error && <ErrorState message={error} />}

      <Modal
        open={dialog === "approve"}
        title="Approve for publication"
        onClose={() => setDialog(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setDialog(null)}>Cancel</button>
            <button
              type="button"
              className="btn-teal"
              disabled={busy !== null || blocking.some((f) => (overrides[f.id] ?? "").trim().length < 10)}
              onClick={() =>
                transition("approve", {
                  comment,
                  overrides: blocking.map((f) => ({ finding_id: f.id, reason: overrides[f.id] ?? "" })),
                })
              }
            >
              Approve
            </button>
          </>
        }
      >
        <div className="space-y-4 text-sm">
          <p>Brand Score {revision.brand_score ?? "—"}. Approving records your name, the time and the AI used on the Review Receipt.</p>
          {blocking.length > 0 && (
            <div className="space-y-3 rounded-xl border border-danger/20 bg-danger-50 p-3">
              <p className="font-semibold text-danger-700">{blocking.length} critical finding(s) are unresolved. Each override needs a written reason (10+ characters) and is highlighted on the receipt.</p>
              {blocking.map((f) => (
                <div key={f.id}>
                  <label htmlFor={`ov-${f.id}`} className="label">
                    {f.rule.id} · “{f.text}”
                  </label>
                  <input id={`ov-${f.id}`} className="input" value={overrides[f.id] ?? ""} onChange={(e) => setOverrides((o) => ({ ...o, [f.id]: e.target.value }))} placeholder="Why is publishing acceptable?" />
                </div>
              ))}
            </div>
          )}
          <div>
            <label htmlFor="approve-note" className="label">Note (optional)</label>
            <textarea id="approve-note" className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          {error && <ErrorState message={error} />}
        </div>
      </Modal>

      <Modal
        open={dialog === "request_changes"}
        title="Request changes"
        onClose={() => setDialog(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" className="btn-primary" disabled={busy !== null || !comment.trim()} onClick={() => transition("request_changes", { comment })}>
              Send back to author
            </button>
          </>
        }
      >
        <label htmlFor="changes-note" className="label">What should the author change? (required)</label>
        <textarea id="changes-note" className="input" rows={4} value={comment} onChange={(e) => setComment(e.target.value)} />
        {error && <div className="mt-2"><ErrorState message={error} /></div>}
      </Modal>
    </div>
  );
}
