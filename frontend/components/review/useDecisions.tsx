"use client";

// Finding decisions (accept, edit, dispute, escalate, undo) with the save lock, the
// reason dialog and the J/K/A/E/D keyboard shortcuts.

import { useEffect, useState } from "react";

import { post } from "@/lib/api";
import type { Finding } from "@/lib/types";

import { ErrorState, Modal } from "../ui";

export type DecisionKind = "accept" | "edit" | "dispute" | "escalate" | "reopen";

interface Options {
  ordered: Finding[];
  focused: string | null;
  onFocus: (id: string) => void;
  canDecide: boolean;
  onChanged: () => Promise<unknown>;
}

export function useDecisions({ ordered, focused, onFocus, canDecide, onChanged }: Options) {
  const [dialog, setDialog] = useState<{ finding: Finding; kind: "edit" | "dispute" | "escalate" } | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);

  async function decide(finding: Finding, kind: DecisionKind, extra: { reason?: string; text?: string } = {}) {
    setBusy(true);
    setSaving(finding.id);
    setError(null);
    try {
      await post(`/api/findings/${finding.id}/decisions`, { kind, ...extra });
      setDialog(null);
      await onChanged(); // keep the note locked until it shows its new status
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
      setSaving(null);
    }
  }

  function start(finding: Finding, kind: DecisionKind) {
    if (saving) return;
    setError(null);
    if (kind === "accept" || kind === "reopen") return void decide(finding, kind);
    setText(kind === "edit" ? finding.suggestion?.text ?? finding.text : "");
    setDialog({ finding, kind });
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (dialog || ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || e.metaKey || e.ctrlKey || e.altKey) return;
      const index = ordered.findIndex((f) => f.id === focused);
      const current = ordered[index];
      const key = e.key.toLowerCase();
      if (key === "j" || key === "k") {
        e.preventDefault();
        const next = ordered[key === "j" ? Math.min(ordered.length - 1, index + 1) : Math.max(0, index - 1)];
        if (next) onFocus(next.id);
      } else if (current && canDecide && current.status === "open") {
        if (key === "a" && current.suggestion) start(current, "accept");
        if (key === "e") start(current, "edit");
        if (key === "d") start(current, "dispute");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const modal = (
    <Modal
      open={dialog !== null}
      onClose={() => setDialog(null)}
      title={dialog?.kind === "edit" ? "Edit the flagged text" : dialog?.kind === "dispute" ? "Dispute this finding" : "Escalate to a reviewer"}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={() => setDialog(null)}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || (dialog?.kind === "dispute" && text.trim().length < 5)}
            onClick={() => dialog && decide(dialog.finding, dialog.kind, dialog.kind === "edit" ? { text } : { reason: text })}
          >
            {dialog?.kind === "edit" ? "Save edit" : dialog?.kind === "dispute" ? "Submit dispute" : "Escalate"}
          </button>
        </>
      }
    >
      {dialog && (
        <div className="space-y-3 text-sm">
          <p className="border-l-2 border-ink bg-paper px-3 py-2">
            <span className="font-mono text-xs font-medium">{dialog.finding.rule.id}</span> “{dialog.finding.text}”
          </p>
          <label htmlFor="decision-text" className="label">
            {dialog.kind === "edit" ? "Replacement text (applied on the next re-check)" : dialog.kind === "dispute" ? "Why is this finding wrong? (required)" : "Note for the reviewer (optional)"}
          </label>
          <textarea id="decision-text" className="input" rows={3} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
          {dialog.kind === "dispute" && <p className="text-xs text-graphite">Disputes are logged and shown to the approver, who can override the finding with a reason.</p>}
          {error && <ErrorState message={error} />}
        </div>
      )}
    </Modal>
  );

  return { start, saving, error: dialog ? null : error, modal };
}
