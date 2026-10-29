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

/** A small numbered pill in the severity colour, matching the margin note's number. */
export function NoteNumber({ n, severity, settled = false, active = false, className }: { n: number; severity: Finding["severity"]; settled?: boolean; active?: boolean; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex h-4 min-w-4 items-center justify-center rounded-full border px-[3px] font-sans text-[10px] font-semibold leading-none tabular-nums transition-colors duration-150",
        settled ? "border-teal-700 text-teal-700" : SEVERITY_STYLE[severity].number,
        active && (settled ? "bg-teal-700 text-sheet" : SEVERITY_STYLE[severity].numberActive),
        className,
      )}
    >
      {n}
    </span>
  );
}

/** The draft as a proof sheet. Each mark carries `data-covers` (the findings it anchors) and
 * is followed by numbered markers; `after` renders content (inline notes on narrow screens)
 * below a block. */
export function DraftView({
  blocks,
  findings,
  numbers,
  focused,
  active,
  onFocus,
  onHover,
  after,
}: {
  blocks: Block[];
  findings: Finding[];
  numbers: Record<string, number>;
  focused: string | null;
  /** The note being pointed at or focused: its mark and marker are highlighted. */
  active: string | null;
  onFocus: (id: string) => void;
  onHover?: (id: string | null) => void;
  after?: (block: Block) => React.ReactNode;
}) {
  return (
    <article className="space-y-4 font-serif text-[17px] leading-[1.85] text-ink" aria-label="Draft with proof marks" data-tour="draft">
      {blocks.map((block) => {
        const mine = findings.filter((f) => f.span.block === block.id && !f.needs_review);
        const placed = new Set<string>();
        return (
          <div key={block.id} data-block={block.id}>
            <p className="whitespace-pre-wrap">
              {segments(block, mine).map((seg, i) => {
                if (!seg.finding) return <span key={i}>{seg.text}</span>;
                const f = seg.finding;
                const open = OPEN.has(f.status);
                const lit = seg.covers?.some((c) => c.id === active || c.id === focused);
                // Each finding gets one marker, after the first mark that anchors it.
                const markers = (seg.covers ?? []).filter((c) => numbers[c.id] && !placed.has(c.id)).sort((a, b) => numbers[a.id] - numbers[b.id]);
                markers.forEach((c) => placed.add(c.id));
                return (
                  <span key={i}>
                    {/* An inline span, not a <button>: a button becomes inline-block and breaks
                        the line flow when a mark wraps. */}
                    <span
                      role="button"
                      tabIndex={0}
                      data-covers={seg.covers?.map((c) => c.id).join(" ")}
                      onClick={() => onFocus(f.id)}
                      onMouseEnter={() => onHover?.(f.id)}
                      onMouseLeave={() => onHover?.(null)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onFocus(f.id);
                        }
                      }}
                      aria-label={`${open ? SEVERITY_STYLE[f.severity].label : "Settled"} finding ${f.rule.id}: ${seg.text}`}
                      className={clsx("cursor-pointer rounded-[2px] [box-decoration-break:clone] focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink", open ? SEVERITY_STYLE[f.severity].mark : "mark-settled", lit && "mark-active")}
                    >
                      {seg.text}
                    </span>
                    {markers.length > 0 && (
                      <span className="relative -top-[0.55em] ml-0.5 inline-flex gap-0.5 align-baseline" aria-hidden="true">
                        {markers.map((c) => (
                          <span key={c.id} data-marker={c.id} onMouseEnter={() => onHover?.(c.id)} onMouseLeave={() => onHover?.(null)} onClick={() => onFocus(c.id)} className="cursor-pointer">
                            <NoteNumber n={numbers[c.id]} severity={c.severity} settled={!OPEN.has(c.status)} active={c.id === active || c.id === focused} />
                          </span>
                        ))}
                      </span>
                    )}
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
