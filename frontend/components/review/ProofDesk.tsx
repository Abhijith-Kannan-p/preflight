"use client";

// The Proof Sheet: the draft set like a printed proof, numbered proof marks on the flagged
// text, and margin notes in the gutter, each level with the line its mark is on and joined to
// its mark by a connector (the active note's at full strength). The sheet grows to the
// height of the notes and its text stays in view beside them. Below 1024px the notes sit
// inline under the paragraph they belong to.

import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { SEVERITY_STYLE } from "@/lib/format";
import type { Block, Finding, Severity } from "@/lib/types";

import { Skeleton } from "../ui";
import { DraftView } from "./DraftView";
import { MarginNote } from "./MarginNote";
import { ProofSummary } from "./ProofSummary";
import { ConnectorLayer, type ConnectorPath, type ConnectorSpec, routeConnectors } from "./connectors";
import { ACCEPT_ALL, useDecisions } from "./useDecisions";

const GAP = 8;
const LINE_NUDGE = 4; // a note's first line sits a little below the top of its text line

export function useWide() {
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

/** Notes in reading order, each as high as its anchor allows without overlapping the one
 * before: notes on the same line stack directly below each other. */
export function placeNotes(items: { id: string; anchor: number; height: number }[]): { tops: Record<string, number>; height: number } {
  const tops: Record<string, number> = {};
  let bottom = 0;
  for (const it of items) {
    const top = Math.max(it.anchor, bottom ? bottom + GAP : 0);
    tops[it.id] = top;
    bottom = top + it.height;
  }
  return { tops, height: bottom };
}

/** Reading-order numbers: block, then position in the block. */
export function numberFindings(findings: Finding[]): Record<string, number> {
  return Object.fromEntries(findings.map((f, i) => [f.id, i + 1]));
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
  const textRef = useRef<HTMLDivElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const noteRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [layout, setLayout] = useState<{ tops: Record<string, number>; height: number } | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [connectors, setConnectors] = useState<ConnectorPath[]>([]);
  const [hidden, setHidden] = useState<Set<Severity>>(new Set());
  const [showReview, setShowReview] = useState(false);

  const main = useMemo(() => findings.filter((f) => !f.needs_review).sort(byPosition), [findings]);
  const numbers = useMemo(() => numberFindings(main), [main]);
  const shown = useMemo(() => main.filter((f) => !hidden.has(f.severity)), [main, hidden]);
  const humanLook = useMemo(() => findings.filter((f) => f.needs_review), [findings]);
  const blockIds = useMemo(() => new Set(blocks.map((b) => b.id)), [blocks]);
  const { start, acceptAll, saving, error, modal } = useDecisions({ ordered: shown, focused, onFocus, canDecide, onChanged });
  const active = hovered ?? focused;

  const measure = useCallback(() => {
    const text = textRef.current;
    const sheet = sheetRef.current;
    if (!wide || !text || !sheet) return setLayout(null);
    // Positions relative to the text block, which stays put relative to its marks even while
    // it is held in view (sticky); the gutter starts where the sheet's padding ends.
    const textTop = text.getBoundingClientRect().top;
    const padTop = parseFloat(getComputedStyle(sheet).paddingTop) || 0;
    const items = shown.map((f) => {
      const mark = text.querySelector<HTMLElement>(`[data-covers~="${f.id}"]`) ?? text.querySelector<HTMLElement>(`[data-block="${f.span.block}"]`);
      const rect = mark?.getClientRects()[0] ?? mark?.getBoundingClientRect();
      return {
        id: f.id,
        anchor: Math.max(0, (rect ? rect.top - textTop : 0) + padTop + LINE_NUDGE),
        height: noteRefs.current[f.id]?.offsetHeight ?? 88,
      };
    });
    const next = placeNotes(items);
    setLayout((prev) => (prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
  }, [wide, shown]);

  useLayoutEffect(() => {
    measure();
  }, [measure, focused]);

  useEffect(() => {
    if (!wide) return;
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    if (textRef.current) observer.observe(textRef.current);
    Object.values(noteRefs.current).forEach((el) => el && observer.observe(el));
    void document.fonts?.ready.then(schedule);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [measure, wide]);

  // A connector for every note on show, redrawn as the page scrolls (the text is sticky, so its
  // marks move against the notes).
  const drawConnectors = useCallback(() => {
    const desk = deskRef.current;
    const sheet = sheetRef.current;
    const gutter = gutterRef.current;
    if (!wide || !desk || !sheet || !gutter || pending) return setConnectors([]);
    const box = desk.getBoundingClientRect();
    const rows = new Map<number, number>();
    const specs: ConnectorSpec[] = [];
    for (const f of shown) {
      const marker = desk.querySelector<HTMLElement>(`[data-marker="${f.id}"]`);
      const mark = desk.querySelector<HTMLElement>(`[data-covers~="${f.id}"]`);
      const note = noteRefs.current[f.id];
      if (!marker || !mark || !note) continue;
      const m = marker.getBoundingClientRect();
      const lines = mark.getClientRects();
      const line = lines[lines.length - 1] ?? mark.getBoundingClientRect();
      // Several marks on one line each take their own row in the line spacing below it.
      const key = Math.round(line.bottom);
      const nth = rows.get(key) ?? 0;
      rows.set(key, nth + 1);
      const badge = note.querySelector<HTMLElement>("[data-badge]")?.getBoundingClientRect() ?? note.getBoundingClientRect();
      specs.push({
        id: f.id,
        colour: OPEN.has(f.status) ? SEVERITY_STYLE[f.severity].stroke : "rgb(var(--teal))",
        start: { x: m.left + m.width / 2 - box.left, y: m.bottom - box.top },
        via: line.bottom - box.top + 3 + nth * 2,
        end: { x: badge.left - box.left, y: badge.top + badge.height / 2 - box.top },
      });
    }
    const next = routeConnectors(specs, { left: sheet.getBoundingClientRect().right - box.left, right: gutter.getBoundingClientRect().left - box.left });
    setConnectors((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
  }, [wide, shown, pending]);

  useLayoutEffect(() => {
    drawConnectors();
  }, [drawConnectors, layout, active]);

  useEffect(() => {
    if (!wide) return;
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(drawConnectors);
    };
    // While notes slide to new places (a 200 ms transition), the lines follow them frame by frame.
    // A deadline rather than a count: a note removed mid-slide never reports the end.
    let until = 0;
    const follow = () => {
      drawConnectors();
      frame = performance.now() < until ? requestAnimationFrame(follow) : 0;
    };
    const onRun = (e: TransitionEvent) => {
      if (e.propertyName !== "top") return;
      until = performance.now() + 260;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(follow);
    };
    const onEnd = (e: TransitionEvent) => {
      if (e.propertyName === "top") schedule();
    };
    const desk = deskRef.current;
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    desk?.addEventListener("transitionrun", onRun);
    desk?.addEventListener("transitionend", onEnd);
    desk?.addEventListener("transitioncancel", onEnd);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      desk?.removeEventListener("transitionrun", onRun);
      desk?.removeEventListener("transitionend", onEnd);
      desk?.removeEventListener("transitioncancel", onEnd);
    };
  }, [drawConnectors, wide]);

  // Bring a note into view when the reader opens one, not for a note open on arrival.
  const initialFocus = useRef(focused);
  useEffect(() => {
    if (focused && focused !== initialFocus.current) noteRefs.current[focused]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    initialFocus.current = null;
  }, [focused]);

  const note = (f: Finding, style?: React.CSSProperties) => (
    <MarginNote
      key={f.id}
      ref={(el) => {
        noteRefs.current[f.id] = el;
      }}
      finding={f}
      number={numbers[f.id]}
      focused={focused === f.id}
      active={active === f.id}
      canDecide={canDecide}
      canEscalate={canEscalate}
      saving={saving === f.id}
      locked={saving !== null}
      onFocus={() => onFocus(focused === f.id ? null : f.id)}
      onHover={(on) => setHovered(on ? f.id : null)}
      onDecide={(kind) => start(f, kind)}
      style={style}
    />
  );

  const orphans = shown.filter((f) => !blockIds.has(f.span.block));
  const padBottom = 32;

  return (
    <div data-tour="findings">
      {!pending && main.length > 0 && (
        <ProofSummary
          findings={main}
          hidden={hidden}
          onToggle={(s) =>
            setHidden((prev) => {
              const next = new Set(prev);
              if (next.has(s)) next.delete(s);
              else next.add(s);
              return next;
            })
          }
          canDecide={canDecide}
          busy={saving === ACCEPT_ALL}
          onAcceptAll={() => void acceptAll(main)}
        />
      )}
      <div ref={deskRef} className="relative grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(300px,360px)] lg:gap-12">
        <section ref={sheetRef} className="proof-paper px-6 py-8 sm:px-10" style={{ minHeight: wide && layout ? layout.height + padBottom + 32 : undefined }} aria-label="Proof sheet">
          <div ref={textRef} className="lg:sticky lg:top-32">
            {header}
            <DraftView
              blocks={blocks}
              findings={pending ? [] : shown}
              numbers={numbers}
              focused={focused}
              active={active}
              onFocus={onFocus}
              onHover={setHovered}
              after={
                wide || pending
                  ? undefined
                  : (block) => {
                      const mine = shown.filter((f) => f.span.block === block.id);
                      return mine.length ? <div className="mt-3 space-y-2 font-sans">{mine.map((f) => note(f))}</div> : null;
                    }
              }
            />
            {!wide && !pending && orphans.length > 0 && <div className="mt-4 space-y-2 font-sans">{orphans.map((f) => note(f))}</div>}
          </div>
        </section>

        <div className="hidden lg:block" aria-label="Margin notes">
          {pending ? (
            <div className="space-y-3 pt-8">
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </div>
          ) : main.length === 0 ? (
            <p className="mt-8 rounded border border-rule border-l-[3px] border-l-cleared bg-sheet px-3 py-2 text-sm text-ink">No marks on this proof. Every check passed and every claim matches an approved fact.</p>
          ) : (
            wide && (
              <div ref={gutterRef} className="relative" style={{ minHeight: layout?.height }}>
                {shown.map((f) => note(f, layout ? { position: "absolute", top: layout.tops[f.id], left: 0, right: 0, transition: "top 200ms ease" } : { marginBottom: GAP }))}
              </div>
            )
          )}
        </div>

        {wide && !pending && <ConnectorLayer paths={connectors} active={active} />}
      </div>

      {error && <p role="alert" className="mt-4 rounded border border-rule border-l-[3px] border-l-signal bg-sheet px-3 py-2 text-sm text-signal-700">{error}</p>}

      {humanLook.length > 0 && !pending && (
        <section className="mt-6 rounded border border-dashed border-rule p-3">
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
