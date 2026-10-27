"use client";

// A finding written as an editor's margin note: severity, rule tag, the fix as a
// before → after, and the decision buttons. Evidence and detail open when focused.

import { clsx } from "clsx";
import { ArrowRight, Check, Flag, Loader2, MessageSquareWarning, Pencil, RotateCcw } from "lucide-react";
import { forwardRef } from "react";

import { SEVERITY_STYLE, driftLabel, pct } from "@/lib/format";
import type { Finding } from "@/lib/types";

import { InfoTip } from "../ui";
import { FactTag, RuleTag } from "./SourcePanel";
import type { DecisionKind } from "./useDecisions";

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  accepted: { text: "Accepted · applies on re-check", className: "border-teal text-teal-700" },
  edited: { text: "Edited · applies on re-check", className: "border-teal text-teal-700" },
  disputed: { text: "Disputed · the approver decides", className: "border-graphite text-graphite" },
  escalated: { text: "Escalated to a reviewer", className: "border-slate text-slate-700" },
  resolved: { text: "Overridden by approver", className: "border-graphite text-graphite" },
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
  /** This note's decision is being saved. */
  saving?: boolean;
  /** Another decision is in flight: hold all buttons until it lands. */
  locked?: boolean;
  onFocus: () => void;
  onDecide: (kind: DecisionKind) => void;
  style?: React.CSSProperties;
}

export const MarginNote = forwardRef<HTMLDivElement, Props>(function MarginNote({ finding: f, focused, canDecide, canEscalate, saving = false, locked = false, onFocus, onDecide, style }, ref) {
  const sev = SEVERITY_STYLE[f.severity];
  const drift = driftLabel(f.suggestion?.drift);
  const status = STATUS_LABEL[f.status];
  const actionable = f.status === "open" || f.status === "escalated";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      onClick={onFocus}
      style={style}
      data-note={f.id}
      className={clsx(
        "scroll-mt-24 border-l-2 bg-sheet py-2.5 pl-3 pr-3 text-sm outline-none transition-[box-shadow,opacity]",
        actionable ? sev.rule : "border-teal",
        focused ? "shadow-sheet ring-1 ring-ink/80" : "hover:ring-1 hover:ring-rule",
        !actionable && !focused && "opacity-75",
      )}
      aria-label={`${sev.label} finding ${f.rule.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={clsx("font-mono text-[11px] font-medium uppercase tracking-wide", actionable ? "text-ink" : "text-graphite")}>
          <span className={clsx("mr-1.5 inline-block h-2 w-2 align-middle", sev.dot)} aria-hidden="true" />
          {sev.label}
        </span>
        <RuleTag id={f.rule.id} source={f.rule.source} />
        <span className="ml-auto flex items-center gap-1 font-mono text-[11px] text-graphite">
          {pct(f.confidence)}
          <InfoTip text={`${DETECTOR[f.detector]}. Below 60% confidence a finding waits for a human look and costs no points.`} />
        </span>
      </div>

      <p className={clsx("mt-1.5 leading-snug text-graphite", !focused && "line-clamp-2")}>{f.explanation}</p>

      {focused && f.evidence.length > 0 && (
        <ul className="mt-2 space-y-1">
          {f.evidence.map((e) => (
            <li key={e.fact_id} className="border-l border-rule pl-2 text-xs leading-snug">
              <FactTag id={e.fact_id} className="mr-1.5" />
              <span className="font-serif text-[13px] text-ink">“{e.quote}”</span>
              {e.nli && <span className="text-graphite"> · NLI {e.nli}{e.score != null && ` ${e.score.toFixed(2)}`}</span>}
            </li>
          ))}
        </ul>
      )}

      {f.suggestion && (
        <p className="mt-2 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5" data-tour="suggestion">
          <span className="text-graphite line-through decoration-signal/70">{f.text}</span>
          <ArrowRight className="h-3 w-3 shrink-0 self-center text-teal" aria-hidden="true" />
          <span className="font-medium text-ink">{f.suggestion.text || "(remove)"}</span>
          {focused && f.suggestion.drift != null && (
            <span className={clsx("ml-auto inline-flex items-center gap-1 font-mono text-[11px]", drift.tone)}>
              {drift.label} {f.suggestion.drift.toFixed(2)}
              <InfoTip text="Drift is how far the change moves the sentence's meaning (1 minus the cosine similarity of sentence embeddings). Low keeps your intent." />
            </span>
          )}
        </p>
      )}

      {status && (
        <p className={clsx("mt-2 border-l-2 pl-2 font-mono text-[11px]", status.className)}>
          {status.text}
          {f.applied_text != null && f.status === "edited" && `: “${f.applied_text}”`}
        </p>
      )}

      {saving && (
        <p role="status" className="mt-2 inline-flex items-center gap-1.5 text-xs text-graphite">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Saving your decision…
        </p>
      )}
      <fieldset disabled={locked} className="mt-2 flex flex-wrap gap-1.5 disabled:opacity-60" onClick={(e) => e.stopPropagation()}>
        {actionable && canDecide && f.suggestion && (
          <button type="button" className="btn-teal px-2 py-1 text-xs" onClick={() => onDecide("accept")}>
            <Check className="h-3.5 w-3.5" aria-hidden="true" /> Accept
          </button>
        )}
        {actionable && canDecide && (
          <>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("edit")}>
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
            </button>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("dispute")}>
              <MessageSquareWarning className="h-3.5 w-3.5" aria-hidden="true" /> Dispute
            </button>
          </>
        )}
        {f.status === "open" && canEscalate && (
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("escalate")}>
            <Flag className="h-3.5 w-3.5" aria-hidden="true" /> Escalate
          </button>
        )}
        {!actionable && f.status !== "resolved" && canDecide && (
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("reopen")}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Undo
          </button>
        )}
      </fieldset>
    </div>
  );
});
