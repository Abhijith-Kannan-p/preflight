"use client";

import { ChevronDown, PartyPopper } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { post } from "@/lib/api";
import type { Finding, Severity } from "@/lib/types";

import { EmptyState, ErrorState, Modal } from "../ui";
import { type DecisionKind, FindingCard } from "./FindingCard";

const GROUPS: { severity: Severity; title: string; hint: string }[] = [
  { severity: "critical", title: "Critical", hint: "Block approval until fixed, or overridden by an approver with a reason." },
  { severity: "major", title: "Major", hint: "Should be fixed before publishing." },
  { severity: "minor", title: "Minor", hint: "Polish." },
];

interface Props {
  findings: Finding[];
  focused: string | null;
  onFocus: (id: string | null) => void;
  canDecide: boolean;
  canEscalate: boolean;
  onChanged: () => void;
}

export function FindingsPanel({ findings, focused, onFocus, canDecide, canEscalate, onChanged }: Props) {
  const refs = useRef<Record<string, HTMLDivElement | null>>({});
  const [dialog, setDialog] = useState<{ finding: Finding; kind: "edit" | "dispute" | "escalate" } | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showReview, setShowReview] = useState(false);

  const main = findings.filter((f) => !f.needs_review);
  const humanLook = findings.filter((f) => f.needs_review);
  const ordered = GROUPS.flatMap((g) => main.filter((f) => f.severity === g.severity));

  useEffect(() => {
    if (focused) refs.current[focused]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused]);

  async function decide(finding: Finding, kind: DecisionKind, extra: { reason?: string; text?: string } = {}) {
    setBusy(true);
    setError(null);
    try {
      await post(`/api/findings/${finding.id}/decisions`, { kind, ...extra });
      setDialog(null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }

  function start(finding: Finding, kind: DecisionKind) {
    setError(null);
    if (kind === "accept" || kind === "reopen") return void decide(finding, kind);
    setText(kind === "edit" ? finding.suggestion?.text ?? finding.text : "");
    setDialog({ finding, kind });
  }

  // Keyboard shortcuts: J/K move, A accept, E edit, D dispute.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (dialog || ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || e.metaKey || e.ctrlKey) return;
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

  if (!findings.length) {
    return <EmptyState icon={<PartyPopper className="h-8 w-8" />} title="No findings" text="Every check passed. This draft is on-brand and every claim matches an approved fact." />;
  }

  return (
    <div className="space-y-6" data-tour="findings">
      {error && !dialog && <ErrorState message={error} />}
      {GROUPS.map((g) => {
        const items = main.filter((f) => f.severity === g.severity);
        if (!items.length) return null;
        return (
          <section key={g.severity} aria-labelledby={`group-${g.severity}`}>
            <h3 id={`group-${g.severity}`} className="mb-2 flex items-baseline gap-2 text-sm font-semibold">
              {g.title} <span className="font-mono text-xs text-navy-500">{items.length}</span>
              <span className="text-xs font-normal text-navy-500">{g.hint}</span>
            </h3>
            <div className="space-y-3">
              {items.map((f) => (
                <FindingCard
                  key={f.id}
                  ref={(el) => {
                    refs.current[f.id] = el;
                  }}
                  finding={f}
                  focused={focused === f.id}
                  canDecide={canDecide}
                  canEscalate={canEscalate}
                  onFocus={() => onFocus(f.id)}
                  onDecide={(kind) => start(f, kind)}
                />
              ))}
            </div>
          </section>
        );
      })}

      {humanLook.length > 0 && (
        <section className="rounded-2xl border border-dashed border-purple/30 p-3">
          <button type="button" onClick={() => setShowReview((s) => !s)} aria-expanded={showReview} className="flex w-full items-center gap-2 text-left text-sm font-semibold">
            <ChevronDown className={`h-4 w-4 transition ${showReview ? "rotate-180" : ""}`} aria-hidden="true" />
            Needs a human look <span className="font-mono text-xs text-navy-500">{humanLook.length}</span>
            <span className="text-xs font-normal text-navy-500">Low confidence: not counted in the score until a person confirms.</span>
          </button>
          {showReview && (
            <div className="mt-3 space-y-3">
              {humanLook.map((f) => (
                <FindingCard key={f.id} finding={f} focused={focused === f.id} canDecide={canDecide} canEscalate={canEscalate} onFocus={() => onFocus(f.id)} onDecide={(kind) => start(f, kind)} />
              ))}
            </div>
          )}
        </section>
      )}

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
              onClick={() =>
                dialog &&
                decide(dialog.finding, dialog.kind, dialog.kind === "edit" ? { text } : { reason: text })
              }
            >
              {dialog?.kind === "edit" ? "Save edit" : dialog?.kind === "dispute" ? "Submit dispute" : "Escalate"}
            </button>
          </>
        }
      >
        {dialog && (
          <div className="space-y-3 text-sm">
            <p className="rounded-xl bg-paper-100 px-3 py-2">
              <span className="font-mono text-xs font-semibold">{dialog.finding.rule.id}</span> “{dialog.finding.text}”
            </p>
            <label htmlFor="decision-text" className="label">
              {dialog.kind === "edit" ? "Replacement text (applied on the next re-check)" : dialog.kind === "dispute" ? "Why is this finding wrong? (required)" : "Note for the reviewer (optional)"}
            </label>
            <textarea id="decision-text" className="input" rows={3} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
            {dialog.kind === "dispute" && <p className="text-xs text-navy-500">Disputes are logged and shown to the approver, who can override the finding with a reason.</p>}
            {error && <ErrorState message={error} />}
          </div>
        )}
      </Modal>
    </div>
  );
}
