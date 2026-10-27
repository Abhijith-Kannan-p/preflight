"use client";

// The landing page's specimen: the Round 1 LinkedIn draft set as a proof, with the margin
// notes a live review produces for it (rules, pages, facts and fixes copied from that run).

import { useState } from "react";

import type { Block, Finding, Severity } from "@/lib/types";

import { ProofDesk } from "./review/ProofDesk";
import { SourceProvider } from "./review/SourcePanel";

const TEXT = "Say hello to India's #1 and 100% secure payments app! Paywise now settles in under 5 seconds for every merchant. Download today and never worry again!";

function note(
  id: string,
  quote: string,
  severity: Severity,
  rule: string,
  page: number,
  explanation: string,
  fix: string,
  confidence: number,
  evidence: Finding["evidence"] = [],
): Finding {
  const start = TEXT.indexOf(quote);
  return {
    id,
    type: "example",
    span: { block: 0, start, end: start + quote.length },
    text: quote,
    rule: { id: rule, source: `brand_book.pdf#p${page}` },
    evidence,
    severity,
    confidence,
    explanation,
    suggestion: { text: fix, drift: null },
    detector: rule.startsWith("CLM") ? "nli" : "rules",
    status: "open",
    needs_review: false,
    related: [],
    applied_text: null,
  };
}

const BLOCKS: Block[] = [{ id: 0, text: TEXT, start_offset: 0 }];

const FINDINGS: Finding[] = [
  note("ex1", "India's #1", "critical", "CLM-01", 13, "A superlative that no approved fact backs.", "India's trusted", 0.9),
  note("ex2", "100% secure", "critical", "CLM-04", 14, "An absolute security claim. No product can promise this; describe the specific protection instead.", "bank-grade encrypted", 0.95, [
    { fact_id: "F-112", quote: "PayWise secures payments with bank-grade AES-256 encryption and is PCI DSS certified.", nli: null, score: null },
  ]),
  note("ex3", "Paywise", "minor", "TRM-02", 8, "The product name is written PayWise.", "PayWise", 0.97),
  note("ex4", "under 5 seconds", "major", "CLM-03", 12, "Matches F-086, which F-087 superseded on 2 Sep 2026.", "under 10 seconds", 0.9, [
    { fact_id: "F-087", quote: "PayWise settles merchant payments in under 10 seconds.", nli: null, score: null },
  ]),
  note("ex5", "never worry again", "major", "CLM-06", 15, "Promises an outcome the brand cannot guarantee.", "pay with confidence", 0.95),
  note("ex6", "Download today and never worry again!", "minor", "TON-03", 5, "At most one exclamation mark for a draft this short.", "Download today and never worry again.", 0.95),
];

const ignore = async () => undefined;

export function LandingProof() {
  const [focused, setFocused] = useState<string | null>("ex2");
  return (
    <SourceProvider>
      <ProofDesk
        blocks={BLOCKS}
        findings={FINDINGS}
        pending={false}
        focused={focused}
        onFocus={setFocused}
        canDecide={false}
        canEscalate={false}
        onChanged={ignore}
        header={
          <p className="mb-6 flex flex-wrap justify-between gap-2 border-b border-rule pb-3 font-mono text-[11px] uppercase tracking-wide text-graphite">
            <span>LinkedIn · launch post · specimen</span>
            <span>Brand Score 24</span>
          </p>
        }
      />
    </SourceProvider>
  );
}
