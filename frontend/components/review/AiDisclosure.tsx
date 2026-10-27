import { Cpu, EyeOff, ShieldCheck } from "lucide-react";

import type { AiSummary, ToneProfile } from "@/lib/types";

const PURPOSE: Record<string, string> = {
  claim_detection: "claim detection",
  tone: "tone scoring",
  suggestions: "suggestion wording",
};

function list(items: string[]): string {
  const named = items.map((p) => PURPOSE[p] ?? p);
  return named.length > 1 ? `${named.slice(0, -1).join(", ")} and ${named.at(-1)}` : (named[0] ?? "");
}

export function AiDisclosure({ ai, tone }: { ai?: AiSummary; tone?: ToneProfile | null }) {
  if (!ai) return <p className="text-sm text-navy-500">The disclosure appears when the review finishes.</p>;
  const hosted = ai.purposes.length > 0;
  return (
    <div className="space-y-4" data-tour="ai">
      <div className="card space-y-3 p-4 text-sm leading-relaxed">
        <p className="flex items-start gap-2">
          <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden="true" />
          <span>
            <strong>AI used: </strong>
            {hosted ? `${list(ai.purposes)} via ${ai.provider}/${ai.model}.` : "no hosted LLM for this review (deterministic mode)."}
            {ai.failed_purposes.length > 0 && <span className="text-amber-700"> {list(ai.failed_purposes)} fell back to deterministic logic after a timeout.</span>}
          </span>
        </p>
        <p className="flex items-start gap-2">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden="true" />
          <span>
            <strong>Verification: </strong>local NLI model {ai.nli_model ?? "unavailable (lexical fallback)"} with exact number comparison and a verbatim quote check; embeddings {ai.embedding_model ?? "unavailable (BM25 only)"}. The LLM never decides whether a claim is true.
          </span>
        </p>
        <p className="flex items-start gap-2">
          <EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden="true" />
          <span>
            <strong>Privacy: </strong>
            {ai.masking_enabled ? `confidential terms, emails, phone numbers and ₹ amounts are masked before any external call. Values masked in this review: ${ai.masked_count}.` : "masking is turned off in Settings."}
          </span>
        </p>
        <p className="text-xs text-navy-500">Suggestions are never applied automatically. A person accepts, edits or disputes each one, and every decision is logged.</p>
      </div>
      {tone && (
        <div className="card p-4">
          <p className="label">Tone profile ({tone.source === "llm" ? "scored by the LLM" : "offline heuristic"})</p>
          <ul className="mt-2 space-y-2">
            {Object.entries(tone.scores).map(([trait, score]) => {
              const target = tone.targets[trait] ?? 0;
              const off = Math.abs(score - target) > 0.3;
              return (
                <li key={trait} className="grid grid-cols-[90px_1fr_80px] items-center gap-3 text-xs">
                  <span className="font-medium capitalize">{trait}</span>
                  <span className="relative h-2 rounded-none bg-paper-100">
                    <span className={`absolute inset-y-0 left-0 rounded-none ${off ? "bg-amber" : "bg-teal"}`} style={{ width: `${score * 100}%` }} />
                    <span className="absolute -top-1 h-4 w-0.5 bg-navy" style={{ left: `${target * 100}%` }} title={`Target ${target}`} />
                  </span>
                  <span className="text-right font-mono text-navy-500">
                    {score.toFixed(2)} / {target.toFixed(2)}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-[11px] text-navy-500">Bar = this draft, line = PayWise target. More than 0.3 apart is flagged under TON-01.</p>
        </div>
      )}
    </div>
  );
}
