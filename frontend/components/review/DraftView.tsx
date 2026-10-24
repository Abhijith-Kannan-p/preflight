"use client";

import { clsx } from "clsx";

import { SEVERITY_STYLE } from "@/lib/format";
import type { Block, Finding } from "@/lib/types";

const RANK = { critical: 3, major: 2, minor: 1 } as const;

interface Segment {
  text: string;
  finding?: Finding;
}

/** Split a block into plain and highlighted segments. Where findings overlap, the most
 * severe one owns the highlight; the others are still listed on the right. */
function segments(block: Block, findings: Finding[]): Segment[] {
  const marks: Finding[] = [];
  const ordered = [...findings].sort((a, b) => RANK[b.severity] - RANK[a.severity] || a.span.start - b.span.start);
  for (const f of ordered) {
    if (marks.every((m) => f.span.end <= m.span.start || f.span.start >= m.span.end)) marks.push(f);
  }
  marks.sort((a, b) => a.span.start - b.span.start);
  const out: Segment[] = [];
  let cursor = 0;
  for (const m of marks) {
    if (m.span.start > cursor) out.push({ text: block.text.slice(cursor, m.span.start) });
    out.push({ text: block.text.slice(m.span.start, m.span.end), finding: m });
    cursor = m.span.end;
  }
  if (cursor < block.text.length) out.push({ text: block.text.slice(cursor) });
  return out;
}

const VISIBLE = new Set(["open", "escalated", "disputed"]);

export function DraftView({
  blocks,
  findings,
  focused,
  onFocus,
}: {
  blocks: Block[];
  findings: Finding[];
  focused: string | null;
  onFocus: (id: string) => void;
}) {
  return (
    <article className="space-y-4 text-[15px] leading-relaxed" aria-label="Draft with highlighted findings" data-tour="draft">
      {blocks.map((block) => {
        const mine = findings.filter((f) => f.span.block === block.id && VISIBLE.has(f.status) && !f.needs_review);
        return (
          <p key={block.id} className="whitespace-pre-wrap">
            {segments(block, mine).map((seg, i) =>
              seg.finding ? (
                <button
                  key={i}
                  type="button"
                  onClick={() => onFocus(seg.finding!.id)}
                  aria-label={`${SEVERITY_STYLE[seg.finding.severity].label} finding ${seg.finding.rule.id}: ${seg.text}`}
                  className={clsx(
                    "rounded px-0.5 text-left underline decoration-2 underline-offset-4 transition",
                    SEVERITY_STYLE[seg.finding.severity].mark,
                    focused === seg.finding.id && "ring-2 ring-navy ring-offset-1 ring-offset-paper-50",
                  )}
                >
                  {seg.text}
                </button>
              ) : (
                <span key={i}>{seg.text}</span>
              ),
            )}
          </p>
        );
      })}
    </article>
  );
}
