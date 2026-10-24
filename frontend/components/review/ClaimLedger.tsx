"use client";

import { ChevronRight, CircleCheck, ListChecks } from "lucide-react";
import { useState } from "react";

import { VERDICT_STYLE, pct } from "@/lib/format";
import type { Claim } from "@/lib/types";

import { Chip, EmptyState, InfoTip } from "../ui";

const ORDER = ["contradicted", "outdated", "unsupported", "needs_review", "supported"];

function Score({ label, value }: { label: string; value: number | string | null | undefined }) {
  if (value == null) return null;
  return (
    <span className="rounded-md bg-paper-100 px-1.5 py-0.5 font-mono text-[10px] text-navy-500">
      {label} {typeof value === "number" ? value.toFixed(2) : value}
    </span>
  );
}

export function ClaimLedger({ claims }: { claims: Claim[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!claims.length) {
    return <EmptyState icon={<ListChecks className="h-8 w-8" />} title="No factual claims found" text="This draft makes no numbers, capability or superlative claims for the ledger to verify." />;
  }
  const sorted = [...claims].sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
  const supported = claims.filter((c) => c.verdict === "supported").length;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-navy-500">
        <CircleCheck className="h-4 w-4 text-teal" aria-hidden="true" />
        {supported} of {claims.length} claims are backed by an approved fact.
        <InfoTip text="Verdicts come from hybrid retrieval, a local NLI model, exact number comparison and a verbatim quote check. The hosted LLM never decides whether a claim is true." />
      </div>
      <div className="overflow-hidden rounded-2xl border border-paper-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper-100 text-xs uppercase tracking-wide text-navy-500">
            <tr>
              <th className="px-3 py-2 font-semibold">Claim</th>
              <th className="px-3 py-2 font-semibold">Verdict</th>
              <th className="hidden px-3 py-2 font-semibold md:table-cell">Evidence</th>
              <th className="px-3 py-2 text-right font-semibold">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-paper-200 bg-paper-50">
            {sorted.map((c) => {
              const style = VERDICT_STYLE[c.verdict];
              const expanded = open === c.id;
              return (
                <tr key={c.id} className="align-top">
                  <td className="px-3 py-3" colSpan={expanded ? 4 : 1}>
                    <p className="font-medium">“{c.text}”</p>
                    <p className="mt-0.5 text-xs text-navy-500">
                      {c.claim_type} · found by {String(c.scores.source ?? "rules") === "llm" ? "LLM extraction" : "pattern rules"}
                    </p>
                    <button type="button" onClick={() => setOpen(expanded ? null : c.id)} aria-expanded={expanded} className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-teal-700 hover:underline">
                      <ChevronRight className={`h-3 w-3 transition ${expanded ? "rotate-90" : ""}`} aria-hidden="true" />
                      How this verdict was reached
                    </button>
                    {expanded && (
                      <div className="mt-2 rounded-xl bg-paper-100 p-3">
                        <ol className="list-decimal space-y-1 pl-5 text-xs leading-relaxed">
                          {c.steps.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ol>
                        <div className="mt-2 flex flex-wrap gap-1">
                          <Score label="entail" value={c.scores.entailment} />
                          <Score label="contra" value={c.scores.contradiction} />
                          <Score label="dense" value={c.scores.dense} />
                          <Score label="bm25" value={c.scores.bm25} />
                          <Score label="numbers" value={c.scores.numeric} />
                        </div>
                      </div>
                    )}
                  </td>
                  {!expanded && (
                    <>
                      <td className="px-3 py-3">
                        <Chip className={style.chip}>{style.label}</Chip>
                      </td>
                      <td className="hidden px-3 py-3 text-xs md:table-cell">
                        {c.fact_id ? (
                          <>
                            <span className="font-mono font-semibold">{c.fact_id}</span>
                            {c.current_fact_id && c.current_fact_id !== c.fact_id && <span className="text-navy-500"> → current {c.current_fact_id}</span>}
                            {c.quote && <span className="mt-0.5 block text-navy-500">“{c.quote}”</span>}
                          </>
                        ) : (
                          <span className="text-navy-300">No matching fact</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-xs">{pct(c.confidence)}</td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
