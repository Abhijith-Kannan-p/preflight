"use client";

// The Proof Sheet: the draft set like a printed proof, proof marks on the flagged text,
// and margin notes in the gutter joined to their marks by leader lines. Below 1024px the
// notes sit inline under the paragraph they belong to.

import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { SEVERITY_STYLE } from "@/lib/format";
import type { Block, Finding, Severity } from "@/lib/types";

import { Skeleton } from "../ui";
import { DraftView } from "./DraftView";
import { MarginNote } from "./MarginNote";
import { useDecisions } from "./useDecisions";

const GAP = 10;
const NOTE_OFFSET = 14; // the leader line meets a note this far below its top edge

function useWide() {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    const update = () => setWide(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

interface Leader {
  id: string;
  severity: Severity;
  open: boolean;
  ax: number;
  ay: number;
  edge: number;
  nx: number;
  ny: number;
}

interface Layout {
  tops: Record<string, number>;
  leaders: Leader[];
  height: number;
}

/** Place notes as close to their anchors as possible without overlapping. The focused note
 * sits on its anchor and the others move around it. */
export function placeNotes(items: { id: string; anchor: number; height: number }[], focused: string | null): Record<string, number> {
  const tops = items.map((it) => Math.max(0, it.anchor - NOTE_OFFSET));
  const pivot = Math.max(0, items.findIndex((it) => it.id === focused));
  for (let i = pivot + 1; i < items.length; i++) tops[i] = Math.max(tops[i], tops[i - 1] + items[i - 1].height + GAP);
  for (let i = pivot - 1; i >= 0; i--) tops[i] = Math.min(tops[i], tops[i + 1] - items[i].height - GAP);
  // Anything pushed above the top edge flows back down.
  for (let i = 0; i < items.length; i++) tops[i] = Math.max(tops[i], i ? tops[i - 1] + items[i - 1].height + GAP : 0);
  return Object.fromEntries(items.map((it, i) => [it.id, tops[i]]));
}

const OPEN = new Set(["open", "escalated", "disputed"]);
const byPosition = (a: Finding, b: Finding) => a.span.block - b.span.block || a.span.start - b.span.start;

interface Props {
  blocks: Block[];
  findings: Finding[];
  pending: boolean;
  focused: string | null;
  onFocus: (id: string | null) => void;
  canDecide: boolean;
  canEscalate: boolean;
  onChanged: () => Promise<unknown>;
  header?: React.ReactNode;
}

export function ProofDesk({ blocks, findings, pending, focused, onFocus, canDecide, canEscalate, onChanged, header }: Props) {
  const wide = useWide();
  const deskRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const noteRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [layout, setLayout] = useState<Layout | null>(null);
  const [showReview, setShowReview] = useState(false);

  const main = useMemo(() => findings.filter((f) => !f.needs_review).sort(byPosition), [findings]);
  const humanLook = useMemo(() => findings.filter((f) => f.needs_review), [findings]);
  const blockIds = useMemo(() => new Set(blocks.map((b) => b.id)), [blocks]);
  const { start, saving, error, modal } = useDecisions({ ordered: main, focused, onFocus, canDecide, onChanged });

  const measure = useCallback(() => {
    const desk = deskRef.current;
    const sheet = sheetRef.current;
    const gutter = gutterRef.current;
    if (!wide || !desk || !sheet || !gutter) return setLayout(null);
    const box = desk.getBoundingClientRect();
    const sheetBox = sheet.getBoundingClientRect();
    const gutterLeft = gutter.getBoundingClientRect().left - box.left;
    const edge = sheetBox.right - box.left;
    const anchors = main.map((f) => {
      const mark = desk.querySelector<HTMLElement>(`[data-covers~="${f.id}"]`);
      const host = mark ?? desk.querySelector<HTMLElement>(`[data-block="${f.span.block}"]`) ?? sheet;
      const rect = (mark?.getClientRects()[0] ?? host.getBoundingClientRect()) as DOMRect;
      return {
        id: f.id,
        ax: mark ? rect.right - box.left : edge - 24,
        anchor: rect.top - box.top + rect.height / 2,
        height: noteRefs.current[f.id]?.offsetHeight ?? 96,
      };
    });
    const sorted = [...anchors].sort((a, b) => a.anchor - b.anchor);
    const gutterTop = gutter.getBoundingClientRect().top - box.top;
    const tops = placeNotes(sorted.map((a) => ({ ...a, anchor: a.anchor - gutterTop })), focused);
    const leaders = sorted.map((a) => {
      const f = main.find((x) => x.id === a.id)!;
      return { id: a.id, severity: f.severity, open: OPEN.has(f.status), ax: a.ax, ay: a.anchor, edge, nx: gutterLeft, ny: gutterTop + tops[a.id] + NOTE_OFFSET };
    });
    const last = sorted.at(-1);
    const height = last ? tops[last.id] + last.height : 0;
    setLayout((prev) => {
      const next = { tops, leaders, height };
      return prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
    });
  }, [wide, main, focused]);

  useLayoutEffect(() => {
    measure();
  }, [measure]);

  useEffect(() => {
    const desk = deskRef.current;
    if (!desk || !wide) return;
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(desk);
    if (sheetRef.current) observer.observe(sheetRef.current);
    Object.values(noteRefs.current).forEach((el) => el && observer.observe(el));
    void document.fonts?.ready.then(schedule);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [measure, wide]);

  useEffect(() => {
    if (focused) noteRefs.current[focused]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused]);

  const note = (f: Finding, style?: React.CSSProperties) => (
    <MarginNote
      key={f.id}
      ref={(el) => {
        noteRefs.current[f.id] = el;
      }}
      finding={f}
      focused={focused === f.id}
      canDecide={canDecide}
      canEscalate={canEscalate}
      saving={saving === f.id}
      locked={saving !== null}
      onFocus={() => onFocus(f.id)}
      onDecide={(kind) => start(f, kind)}
      style={style}
    />
  );

  const counts = (["critical", "major", "minor"] as const).map((s) => [s, main.filter((f) => f.severity === s && OPEN.has(f.status)).length] as const);
  const orphans = main.filter((f) => !blockIds.has(f.span.block));

  return (
    <div data-tour="findings">
      <div ref={deskRef} className="relative grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]">
        <section ref={sheetRef} className="sheet h-fit px-6 py-8 sm:px-10" aria-label="Proof sheet">
          {header}
          <DraftView
            blocks={blocks}
            findings={pending ? [] : main}
            focused={focused}
            onFocus={onFocus}
            after={wide || pending ? undefined : (block) => {
              const mine = main.filter((f) => f.span.block === block.id);
              return mine.length ? <div className="mt-3 space-y-2 border-l border-rule pl-3 font-sans">{mine.map((f) => note(f))}</div> : null;
            }}
          />
          {!wide && !pending && orphans.length > 0 && <div className="mt-4 space-y-2 border-l border-rule pl-3">{orphans.map((f) => note(f))}</div>}
          <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule pt-3 text-[11px] text-graphite">
            <span><span className="mark-critical">wavy</span> critical</span>
            <span><span className="mark-major">underline</span> major</span>
            <span><span className="mark-minor">dotted</span> minor</span>
            <span><span className="mark-settled">thin</span> settled</span>
            <span className="ml-auto font-mono">J / K move · A accept · E edit · D dispute · ? help</span>
          </div>
        </section>

        <div className="hidden lg:block" aria-label="Margin notes">
          <p className="label flex flex-wrap items-center gap-x-3">
            Margin notes
            {!pending &&
              counts.map(([s, n]) => (
                <span key={s} className="font-mono normal-case tracking-normal">
                  <span className={clsx("mr-1 inline-block h-1.5 w-1.5 align-middle", SEVERITY_STYLE[s].dot)} aria-hidden="true" />
                  {n} {s}
                </span>
              ))}
          </p>
          {pending ? (
            <div className="space-y-3">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
          ) : main.length === 0 ? (
            <p className="border-l-2 border-cleared bg-sheet px-3 py-2 text-sm text-ink">No marks on this proof. Every check passed and every claim matches an approved fact.</p>
          ) : (
            wide && (
              <div ref={gutterRef} className="relative" style={{ minHeight: layout?.height }}>
                {main.map((f) => note(f, layout ? { position: "absolute", top: layout.tops[f.id], left: 0, right: 0, transition: "top 200ms ease" } : { marginBottom: GAP }))}
              </div>
            )
          )}
        </div>

        {wide && layout && !pending && (
          <svg className="pointer-events-none absolute inset-0 hidden h-full w-full lg:block" aria-hidden="true">
            {layout.leaders.map((l) => {
              const active = l.id === focused;
              const colour = l.open ? SEVERITY_STYLE[l.severity].stroke : "rgb(var(--teal))";
              return (
                <g key={l.id} opacity={active ? 1 : 0.5}>
                  {active && <path d={`M ${l.ax} ${l.ay + 6} L ${l.edge} ${l.ay + 6}`} stroke={colour} strokeWidth="1" strokeDasharray="2 3" fill="none" />}
                  <path d={`M ${l.edge} ${l.ay + 6} L ${l.edge + 10} ${l.ay + 6} L ${l.nx - 6} ${l.ny} L ${l.nx} ${l.ny}`} stroke={colour} strokeWidth={active ? 1.25 : 0.75} fill="none" />
                  <circle cx={l.edge} cy={l.ay + 6} r="2" fill={colour} />
                </g>
              );
            })}
          </svg>
        )}
      </div>

      {error && <p role="alert" className="mt-4 border-l-2 border-signal bg-sheet px-3 py-2 text-sm text-signal-700">{error}</p>}

      {humanLook.length > 0 && !pending && (
        <section className="mt-6 border border-dashed border-rule p-3">
          <button type="button" onClick={() => setShowReview((s) => !s)} aria-expanded={showReview} className="flex w-full items-center gap-2 text-left text-sm font-medium">
            <ChevronDown className={clsx("h-4 w-4 transition", showReview && "rotate-180")} aria-hidden="true" />
            Needs a human look <span className="font-mono text-xs text-graphite">{humanLook.length}</span>
            <span className="text-xs font-normal text-graphite">Low confidence: not counted in the score until a person confirms.</span>
          </button>
          {showReview && <div className="mt-3 grid gap-2 md:grid-cols-2">{humanLook.map((f) => note(f))}</div>}
        </section>
      )}
      {modal}
    </div>
  );
}
