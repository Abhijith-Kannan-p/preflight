"use client";

import { clsx } from "clsx";

import { SEVERITY_STYLE } from "@/lib/format";
import type { Block, Finding } from "@/lib/types";

const RANK = { critical: 3, major: 2, minor: 1 } as const;
const OPEN = new Set(["open", "escalated", "disputed"]);

interface Segment {
  text: string;
  finding?: Finding;
  covers?: Finding[];
}

/** Split a block into plain and marked segments. Where findings overlap, the most severe
 * open one owns the proof mark; the others are anchored to it through `covers`. */
function segments(block: Block, findings: Finding[]): Segment[] {
  const marks: Finding[] = [];
  const weight = (f: Finding) => (OPEN.has(f.status) ? 10 : 0) + RANK[f.severity];
  const ordered = findings.filter((f) => f.span.end > f.span.start).sort((a, b) => weight(b) - weight(a) || a.span.start - b.span.start);
  for (const f of ordered) {
    if (marks.every((m) => f.span.end <= m.span.start || f.span.start >= m.span.end)) marks.push(f);
  }
  marks.sort((a, b) => a.span.start - b.span.start);
  const out: Segment[] = [];
  let cursor = 0;
  for (const m of marks) {
    if (m.span.start > cursor) out.push({ text: block.text.slice(cursor, m.span.start) });
    const covers = findings.filter((f) => f.span.start < m.span.end && f.span.end > m.span.start);
    out.push({ text: block.text.slice(m.span.start, m.span.end), finding: m, covers });
    cursor = m.span.end;
  }
  if (cursor < block.text.length) out.push({ text: block.text.slice(cursor) });
  return out;
}

/** The draft as a proof sheet. Marks carry `data-covers` so margin notes can draw leader
 * lines to them; `after` renders content (inline notes on narrow screens) below a block. */
export function DraftView({
  blocks,
  findings,
  focused,
  onFocus,
  after,
}: {
  blocks: Block[];
  findings: Finding[];
  focused: string | null;
  onFocus: (id: string) => void;
  after?: (block: Block) => React.ReactNode;
}) {
  return (
    <article className="space-y-4 font-serif text-[17px] leading-[1.7] text-ink" aria-label="Draft with proof marks" data-tour="draft">
      {blocks.map((block) => {
        const mine = findings.filter((f) => f.span.block === block.id && !f.needs_review);
        return (
          <div key={block.id} data-block={block.id}>
            <p className="whitespace-pre-wrap">
              {segments(block, mine).map((seg, i) => {
                if (!seg.finding) return <span key={i}>{seg.text}</span>;
                const f = seg.finding;
                const open = OPEN.has(f.status);
                const active = seg.covers?.some((c) => c.id === focused);
                return (
                  // An inline span, not a <button>: a button becomes inline-block and breaks
                  // the line flow when a mark wraps.
                  <span
                    key={i}
                    role="button"
                    tabIndex={0}
                    data-covers={seg.covers?.map((c) => c.id).join(" ")}
                    onClick={() => onFocus(f.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onFocus(f.id);
                      }
                    }}
                    aria-label={`${open ? SEVERITY_STYLE[f.severity].label : "Settled"} finding ${f.rule.id}: ${seg.text}`}
                    className={clsx("cursor-pointer [box-decoration-break:clone] focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink", open ? SEVERITY_STYLE[f.severity].mark : "mark-settled", active && "mark-active")}
                  >
                    {seg.text}
                  </span>
                );
              })}
            </p>
            {after?.(block)}
          </div>
        );
      })}
    </article>
  );
}
