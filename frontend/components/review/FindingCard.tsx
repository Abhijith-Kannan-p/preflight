"use client";

import { clsx } from "clsx";
import { ArrowRight, BookOpen, Check, Flag, MessageSquareWarning, Pencil, Quote, RotateCcw } from "lucide-react";
import { forwardRef } from "react";

import { SEVERITY_STYLE, driftLabel, pct } from "@/lib/format";
import type { Finding } from "@/lib/types";

import { Chip, InfoTip, Tip } from "../ui";

export type DecisionKind = "accept" | "edit" | "dispute" | "escalate" | "reopen";

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  accepted: { text: "Suggestion accepted · applies on re-check", className: "bg-teal-50 text-teal-700" },
  edited: { text: "Edited · applies on re-check", className: "bg-teal-50 text-teal-700" },
  disputed: { text: "Disputed · an approver will decide", className: "bg-purple-50 text-purple-700" },
  escalated: { text: "Escalated to a reviewer", className: "bg-info-50 text-info-700" },
  resolved: { text: "Overridden by approver", className: "bg-paper-100 text-navy-500" },
};

const DETECTOR: Record<string, string> = {
  rules: "Deterministic rule",
  nli: "Claim Ledger (retrieval + local NLI)",
  llm: "Hosted LLM (scored, never decides truth)",
};

interface Props {
  finding: Finding;
  focused: boolean;
  canDecide: boolean;
  canEscalate: boolean;
  onFocus: () => void;
  onDecide: (kind: DecisionKind) => void;
}

export const FindingCard = forwardRef<HTMLDivElement, Props>(function FindingCard({ finding: f, focused, canDecide, canEscalate, onFocus, onDecide }, ref) {
  const sev = SEVERITY_STYLE[f.severity];
  const drift = driftLabel(f.suggestion?.drift);
  const status = STATUS_LABEL[f.status];
  const actionable = f.status === "open" || f.status === "escalated";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      onClick={onFocus}
      className={clsx("card scroll-mt-24 p-4 outline-none transition", focused ? "ring-2 ring-navy" : "hover:shadow-lift", !actionable && "opacity-80")}
      aria-label={`${sev.label} finding ${f.rule.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Chip className={sev.chip}>
          <span className={clsx("h-1.5 w-1.5 rounded-full", sev.dot)} aria-hidden="true" />
          {sev.label}
        </Chip>
        <Tip text={`Source: ${f.rule.source}`}>
          <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-navy">
            <BookOpen className="h-3 w-3 text-navy-500" aria-hidden="true" /> {f.rule.id}
          </span>
        </Tip>
        <span className="text-xs text-navy-500">{f.rule.source.replace("#p", " p")}</span>
        <span className="ml-auto flex items-center gap-1 text-xs text-navy-500">
          {pct(f.confidence)} confident
          <InfoTip text={`${DETECTOR[f.detector]}. Below 60% a finding waits for a human look and costs no points.`} />
        </span>
      </div>

      <p className="mt-2 text-sm font-semibold text-navy">“{f.text}”</p>
      <p className="mt-1 text-sm leading-relaxed text-navy-500">{f.explanation}</p>

      {f.evidence.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {f.evidence.map((e) => (
            <li key={e.fact_id} className="flex items-start gap-2 rounded-xl bg-paper-100 px-3 py-2 text-xs">
              <Quote className="mt-0.5 h-3 w-3 shrink-0 text-navy-500" aria-hidden="true" />
              <span>
                <span className="font-mono font-semibold">{e.fact_id}</span> “{e.quote}”
                {e.nli && (
                  <span className="text-navy-500">
                    {" "}
                    · NLI {e.nli}
                    {e.score != null && ` ${e.score.toFixed(2)}`}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {f.suggestion && (
        <div className="mt-3 rounded-xl border border-teal/20 bg-teal-50/60 px-3 py-2 text-sm" data-tour="suggestion">
          <div className="flex items-center gap-2 text-xs font-semibold text-teal-700">
            Suggestion
            <span className={clsx("ml-auto font-medium", drift.tone)}>
              {drift.label}
              {f.suggestion.drift != null && ` (${f.suggestion.drift.toFixed(2)})`}
            </span>
            <InfoTip text="Drift = how far the change moves the sentence's meaning (1 − cosine similarity of sentence embeddings). Low keeps your intent." />
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="text-navy-500 line-through decoration-danger/60">{f.text}</span>
            <ArrowRight className="h-3.5 w-3.5 text-teal" aria-hidden="true" />
            <span className="font-semibold text-navy">{f.suggestion.text || "(remove)"}</span>
          </p>
        </div>
      )}

      {status && (
        <p className={clsx("mt-3 rounded-lg px-2 py-1 text-xs font-medium", status.className)}>
          {status.text}
          {f.applied_text != null && f.status === "edited" && `: “${f.applied_text}”`}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
        {actionable && canDecide && f.suggestion && (
          <button type="button" className="btn-teal py-1.5 text-xs" onClick={() => onDecide("accept")}>
            <Check className="h-3.5 w-3.5" aria-hidden="true" /> Accept
          </button>
        )}
        {actionable && canDecide && (
          <>
            <button type="button" className="btn-ghost py-1.5 text-xs" onClick={() => onDecide("edit")}>
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
            </button>
            <button type="button" className="btn-ghost py-1.5 text-xs" onClick={() => onDecide("dispute")}>
              <MessageSquareWarning className="h-3.5 w-3.5" aria-hidden="true" /> Dispute
            </button>
          </>
        )}
        {f.status === "open" && canEscalate && (
          <button type="button" className="btn-ghost py-1.5 text-xs" onClick={() => onDecide("escalate")}>
            <Flag className="h-3.5 w-3.5" aria-hidden="true" /> Escalate
          </button>
        )}
        {!actionable && f.status !== "resolved" && canDecide && (
          <button type="button" className="btn-ghost py-1.5 text-xs" onClick={() => onDecide("reopen")}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Undo
          </button>
        )}
      </div>
    </div>
  );
});
