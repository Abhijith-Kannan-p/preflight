"use client";

// A finding written as an editor's margin note. Compact by default: its number, severity, a
// one-line reason, the fix as a before → after, and Accept. Expanded (click or Enter): the
// rule and its source, confidence, the evidence, and Edit / Dispute / Escalate.

import { clsx } from "clsx";
import { AlertOctagon, AlertTriangle, ArrowRight, Check, ChevronDown, Flag, Info, Loader2, MessageSquareWarning, Pencil, RotateCcw } from "lucide-react";
import { forwardRef } from "react";

import { SEVERITY_STYLE, driftLabel, pct } from "@/lib/format";
import type { Finding, Severity } from "@/lib/types";

import { InfoTip } from "../ui";
import { NoteNumber } from "./DraftView";
import { FactTag, RuleTag } from "./SourcePanel";
import type { DecisionKind } from "./useDecisions";

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  accepted: { text: "Accepted · applies on re-check", className: "border-teal text-teal-700" },
  edited: { text: "Edited · applies on re-check", className: "border-teal text-teal-700" },
  disputed: { text: "Disputed · the approver decides", className: "border-graphite text-graphite" },
  escalated: { text: "Escalated to a reviewer", className: "border-teal text-teal-700" },
  resolved: { text: "Overridden by approver", className: "border-graphite text-graphite" },
};

const DETECTOR: Record<string, string> = {
  rules: "Deterministic rule",
  nli: "Claim Ledger (retrieval + local NLI)",
  llm: "Hosted LLM (scored, never decides truth)",
};

export const SEVERITY_ICON: Record<Severity, typeof Info> = { critical: AlertOctagon, major: AlertTriangle, minor: Info };

interface Props {
  finding: Finding;
  /** Reading-order number, shown on the note and on its marker in the text. */
  number?: number;
  /** Expanded: the note the reader has opened (J/K, click or Enter). */
  focused: boolean;
  /** Highlighted together with its mark while pointed at. */
  active?: boolean;
  canDecide: boolean;
  canEscalate: boolean;
  /** This note's decision is being saved. */
  saving?: boolean;
  /** Another decision is in flight: hold all buttons until it lands. */
  locked?: boolean;
  onFocus: () => void;
  onHover?: (on: boolean) => void;
  onDecide: (kind: DecisionKind) => void;
  style?: React.CSSProperties;
}

export const MarginNote = forwardRef<HTMLDivElement, Props>(function MarginNote(
  { finding: f, number, focused, active = false, canDecide, canEscalate, saving = false, locked = false, onFocus, onHover, onDecide, style },
  ref,
) {
  const sev = SEVERITY_STYLE[f.severity];
  const Icon = SEVERITY_ICON[f.severity];
  const drift = driftLabel(f.suggestion?.drift);
  const status = STATUS_LABEL[f.status];
  const actionable = f.status === "open" || f.status === "escalated";
  return (
    <div
      ref={ref}
      tabIndex={0}
      onClick={onFocus}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      onFocus={() => onHover?.(true)}
      onBlur={() => onHover?.(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) {
          e.preventDefault();
          onFocus();
        }
      }}
      style={style}
      data-note={f.id}
      className={clsx(
        "scroll-mt-28 rounded border border-l-[3px] bg-sheet px-3 py-2.5 text-sm outline-none transition-[box-shadow,opacity,border-color] duration-150 focus-visible:ring-2 focus-visible:ring-teal",
        actionable ? sev.rule : "border-l-teal",
        focused ? "border-y-rule border-r-rule shadow-lift" : active ? "border-y-graphite/40 border-r-graphite/40" : "border-y-rule border-r-rule hover:border-y-graphite/40 hover:border-r-graphite/40",
        !actionable && !focused && "opacity-80",
      )}
      aria-label={`${sev.label} finding ${f.rule.id}`}
    >
      <div className="flex items-center gap-2">
        {number != null && <NoteNumber n={number} severity={f.severity} settled={!actionable} active={active || focused} />}
        <span className={clsx("inline-flex items-center gap-1 text-xs font-semibold", actionable ? sev.text : "text-teal-700")}>
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {sev.label}
        </span>
        {focused && <RuleTag id={f.rule.id} source={f.rule.source} />}
        <span className="ml-auto flex items-center gap-1 text-graphite">
          {focused && (
            <span className="flex items-center gap-1 font-mono text-[11px]">
              {pct(f.confidence)}
              <InfoTip text={`${DETECTOR[f.detector]}. Below 60% confidence a finding waits for a human look and costs no points.`} />
            </span>
          )}
          <ChevronDown className={clsx("h-3.5 w-3.5 transition-transform duration-150", focused && "rotate-180")} aria-hidden="true" />
        </span>
      </div>

      <p className={clsx("mt-1 leading-snug text-graphite", !focused && "line-clamp-1")}>{f.explanation}</p>

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
        <p className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5" data-tour="suggestion">
          <span className="text-graphite line-through decoration-signal/70">{f.text}</span>
          <ArrowRight className="h-3 w-3 shrink-0 self-center text-teal-700" aria-hidden="true" />
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
        <p className={clsx("mt-2 border-l-2 pl-2 text-xs", status.className)}>
          {status.text}
          {f.applied_text != null && f.status === "edited" && `: “${f.applied_text}”`}
        </p>
      )}

      {saving && (
        <p role="status" className="mt-2 inline-flex items-center gap-1.5 text-xs text-graphite">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Saving your decision…
        </p>
      )}
      <fieldset disabled={locked} className="mt-2 flex flex-wrap gap-1.5 empty:hidden disabled:opacity-60" onClick={(e) => e.stopPropagation()}>
        {actionable && canDecide && f.suggestion && (
          <button type="button" className="btn-teal px-2.5 py-1 text-xs" onClick={() => onDecide("accept")}>
            <Check className="h-3.5 w-3.5" aria-hidden="true" /> Accept
          </button>
        )}
        {focused && actionable && canDecide && (
          <>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("edit")}>
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
            </button>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("dispute")}>
              <MessageSquareWarning className="h-3.5 w-3.5" aria-hidden="true" /> Dispute
            </button>
          </>
        )}
        {focused && f.status === "open" && canEscalate && (
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("escalate")}>
            <Flag className="h-3.5 w-3.5" aria-hidden="true" /> Escalate
          </button>
        )}
        {!actionable && f.status !== "resolved" && canDecide && (
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => onDecide("reopen")}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Undo
          </button>
        )}
        {!focused && actionable && canDecide && (
          <button type="button" className="px-1 py-1 text-xs text-graphite underline decoration-rule underline-offset-2 hover:text-ink hover:decoration-ink" onClick={onFocus}>
            More
          </button>
        )}
      </fieldset>
    </div>
  );
});
