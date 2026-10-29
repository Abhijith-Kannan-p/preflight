"use client";

// The Proof Desk for images and scans: the page with boxes for each finding (and, on request,
// every line OCR read and the logo it found), margin notes beside it, the palette compared
// with the brand colours, every text line's measured contrast, and the text read from the
// image set as a proof sheet.

import { clsx } from "clsx";
import { useEffect, useMemo, useState } from "react";

import { API_URL } from "@/lib/api";
import { SEVERITY_STYLE } from "@/lib/format";
import type { Block, Finding, Region, Report, Severity, VisualPage } from "@/lib/types";

import { Skeleton } from "../ui";
import { DraftView, NoteNumber } from "./DraftView";
import { MarginNote } from "./MarginNote";
import { numberFindings } from "./ProofDesk";
import { ProofSummary } from "./ProofSummary";
import { ACCEPT_ALL, useDecisions } from "./useDecisions";

const OPEN = new Set(["open", "escalated", "disputed"]);

function box(region: Region): React.CSSProperties {
  return { left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.w * 100}%`, height: `${region.h * 100}%` };
}

function Swatch({ hex, className }: { hex: string; className?: string }) {
  return <span className={clsx("inline-block h-4 w-4 shrink-0 border border-ink/15", className)} style={{ background: hex }} aria-hidden="true" />;
}

interface Props {
  blocks: Block[];
  findings: Finding[];
  report: Report;
  pending: boolean;
  focused: string | null;
  onFocus: (id: string | null) => void;
  canDecide: boolean;
  canEscalate: boolean;
  onChanged: () => Promise<unknown>;
  header?: React.ReactNode;
}

export function VisualDesk({ blocks, findings, report, pending, focused, onFocus, canDecide, canEscalate, onChanged, header }: Props) {
  const visual = report.visual;
  const [pageIndex, setPageIndex] = useState(0);
  const [layers, setLayers] = useState({ findings: true, ocr: false, logo: true });
  const main = useMemo(
    () =>
      findings
        .filter((f) => !f.needs_review)
        .sort((a, b) => (a.region?.page ?? 0) - (b.region?.page ?? 0) || (a.region?.y ?? 2) - (b.region?.y ?? 2)),
    [findings],
  );
  const numbers = useMemo(() => numberFindings(main), [main]);
  const [hidden, setHidden] = useState<Set<Severity>>(new Set());
  const [hovered, setHovered] = useState<string | null>(null);
  const shown = useMemo(() => main.filter((f) => !hidden.has(f.severity)), [main, hidden]);
  const { start, acceptAll, saving, error, modal } = useDecisions({ ordered: shown, focused, onFocus, canDecide, onChanged });
  const active = hovered ?? focused;

  // Focusing a note on another page turns to that page.
  useEffect(() => {
    const target = main.find((f) => f.id === focused);
    if (target?.region) setPageIndex(target.region.page);
  }, [focused, main]);

  const page: VisualPage | undefined = visual?.pages[pageIndex];
  const onPage = shown.filter((f) => f.region && f.region.page === pageIndex);
  const elsewhere = shown.filter((f) => !f.region);

  const note = (f: Finding) => (
    <MarginNote
      key={f.id}
      finding={f}
      number={numbers[f.id]}
      focused={focused === f.id}
      active={active === f.id}
      onHover={(on) => setHovered(on ? f.id : null)}
      canDecide={canDecide}
      canEscalate={canEscalate}
      saving={saving === f.id}
      locked={saving !== null}
      onFocus={() => onFocus(focused === f.id ? null : f.id)}
      onDecide={(kind) => start(f, kind)}
    />
  );

  return (
    <div data-tour="findings" className="space-y-6">
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
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]">
        <section className="proof-paper h-fit px-4 py-6 sm:px-8" aria-label="Visual proof">
          {header}
          {pending || !page ? (
            <Skeleton className="aspect-[1.9] w-full" />
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-graphite">
                {visual && visual.pages.length > 1 && (
                  <span className="flex gap-1" role="tablist" aria-label="Pages">
                    {visual.pages.map((p) => (
                      <button key={p.index} type="button" role="tab" aria-selected={p.index === pageIndex} onClick={() => setPageIndex(p.index)} className={clsx("tag", p.index === pageIndex && "border-ink")}>
                        p{p.index + 1}
                      </button>
                    ))}
                  </span>
                )}
                <span className="label mb-0">Show</span>
                {(
                  [
                    ["findings", "Findings"],
                    ["ocr", "Text read (OCR)"],
                    ["logo", "Logo"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key} className="inline-flex cursor-pointer items-center gap-1.5">
                    <input type="checkbox" className="accent-ink" checked={layers[key]} onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))} />
                    {label}
                  </label>
                ))}
              </div>
              <figure className="relative w-full overflow-hidden border border-rule bg-paper" style={{ aspectRatio: `${page.width} / ${page.height}` }}>
                {/* eslint-disable-next-line @next/next/no-img-element -- dynamic API image, sized by its own aspect ratio */}
                <img src={`${API_URL}/api/assets/${page.asset_id}`} alt="The reviewed visual" className="absolute inset-0 h-full w-full" />
                {layers.ocr &&
                  page.contrast.map((c, i) => (
                    <span key={`ocr-${i}`} className="pointer-events-none absolute border border-dashed border-slate/80" style={box(c.region)} aria-hidden="true" />
                  ))}
                {layers.logo && page.logo && (
                  <>
                    <span className="pointer-events-none absolute border-2 border-teal" style={box(page.logo.region)} aria-hidden="true" />
                    {page.logo.clear_space && <span className="pointer-events-none absolute border border-dashed border-teal" style={box(page.logo.clear_space.region)} aria-hidden="true" />}
                  </>
                )}
                {layers.findings &&
                  onPage.map((f) => {
                    const lit = active === f.id;
                    const open = OPEN.has(f.status);
                    return (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => onFocus(f.id)}
                        onMouseEnter={() => setHovered(f.id)}
                        onMouseLeave={() => setHovered(null)}
                        aria-label={`${SEVERITY_STYLE[f.severity].label} finding ${f.rule.id} on the image`}
                        className={clsx("absolute border-2 transition-[box-shadow,opacity] duration-150", open ? SEVERITY_STYLE[f.severity].rule : "border-teal", lit ? "z-10 opacity-100 shadow-[0_0_0_3px_rgb(var(--sheet))]" : active ? "opacity-60" : "opacity-80 hover:opacity-100")}
                        style={box(f.region!)}
                      >
                        <span className={clsx("absolute -top-[20px] left-[-2px] inline-flex items-center gap-1 whitespace-nowrap rounded-sm bg-sheet pr-1 font-mono text-[10px] leading-4 text-ink shadow-sm")}>
                          <NoteNumber n={numbers[f.id]} severity={f.severity} settled={!open} active={lit} className="h-4 min-w-4 text-[10px]" />
                          {f.rule.id}
                        </span>
                      </button>
                    );
                  })}
              </figure>
              <p className="mt-2 font-mono text-[11px] text-graphite">
                {page.width}×{page.height} px analysed · OCR {((visual?.timings_ms.ocr ?? 0) / 1000).toFixed(1)} s · {page.lines} line{page.lines === 1 ? "" : "s"} read
              </p>
            </>
          )}
        </section>

        <div aria-label="Margin notes">
          {pending ? (
            <div className="space-y-3">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
          ) : main.length === 0 ? (
            <p className="rounded border border-rule border-l-[3px] border-l-cleared bg-sheet px-3 py-2 text-sm text-ink">No marks on this visual. Colours, contrast, logo, alt text and the text in the image all passed.</p>
          ) : (
            <div className="space-y-2">
              {onPage.map(note)}
              {elsewhere.length > 0 && <p className="label pt-2">About the whole asset</p>}
              {elsewhere.map(note)}
              {visual && visual.pages.length > 1 && main.some((f) => f.region && f.region.page !== pageIndex) && (
                <p className="text-xs text-graphite">Notes on other pages appear when you turn to them.</p>
              )}
            </div>
          )}
          {error && <p role="alert" className="mt-3 border-l-2 border-signal bg-sheet px-3 py-2 text-sm text-signal-700">{error}</p>}
        </div>
      </div>

      {page && !pending && visual && (
        <div className="grid gap-8 lg:grid-cols-2">
          <section aria-labelledby="palette-heading">
            <h3 id="palette-heading" className="label">Colours found vs the brand palette</h3>
            <ul className="divide-y divide-rule border-y border-rule text-sm">
              {page.palette.map((c) => (
                <li key={c.hex} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 py-1.5">
                  <Swatch hex={c.hex} />
                  <span>
                    <span className="font-mono text-xs">{c.hex}</span> <span className="text-graphite">covers {(c.coverage * 100).toFixed(0)}%</span>
                    <span className="block text-xs text-graphite">
                      nearest <Swatch hex={c.nearest.hex} className="h-3 w-3 align-[-2px]" /> {c.nearest.name} · ΔE00 {c.delta_e.toFixed(1)}
                    </span>
                  </span>
                  <span className={clsx("font-mono text-[11px] uppercase", c.off_palette ? "text-signal-700" : "text-cleared-700")}>{c.off_palette ? "off-palette" : "on brand"}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-graphite">
              Brand palette:
              {visual.brand_palette.map((b) => (
                <span key={b.hex} className="inline-flex items-center gap-1" title={`${b.name} ${b.hex}`}>
                  <Swatch hex={b.hex} className="h-3 w-3" />
                </span>
              ))}
              · off-palette means over {(visual.thresholds.off_palette_coverage * 100).toFixed(0)}% of the image and ΔE00 over {visual.thresholds.off_palette_delta_e}.
            </p>
          </section>

          <section aria-labelledby="contrast-heading">
            <h3 id="contrast-heading" className="label">Text contrast (WCAG 2.2 AA)</h3>
            {page.contrast.length === 0 ? (
              <p className="text-sm text-graphite">No text was read in this image.</p>
            ) : (
              <ul className="divide-y divide-rule border-y border-rule text-sm">
                {page.contrast.map((c, i) => (
                  <li key={i} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 py-1.5">
                    <span className="flex h-6 w-9 items-center justify-center border border-ink/15 font-serif text-sm" style={{ background: c.background, color: c.foreground }} aria-hidden="true">
                      Aa
                    </span>
                    <span className="truncate" title={c.text}>
                      {c.text}
                    </span>
                    <span className={clsx("font-mono text-xs", c.passed ? "text-cleared-700" : "text-signal-700")}>
                      {c.ratio.toFixed(1)}:1 {c.passed ? "≥" : "<"} {c.needed}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-xs text-graphite">Large text (a line at least {visual.thresholds.large_text_box_px} px tall at full size) needs 3:1; other text 4.5:1. The logo&apos;s wordmark is checked by the logo rules instead.</p>
          </section>
        </div>
      )}

      {!pending && blocks.length > 0 && (
        <section className="proof-paper px-6 py-6 sm:px-10" aria-label="Text read from the image">
          <p className="label mb-4">Text read from the image · checked like any draft</p>
          <DraftView blocks={blocks} findings={shown} numbers={numbers} focused={focused} active={active} onFocus={onFocus} onHover={setHovered} />
        </section>
      )}
      {modal}
    </div>
  );
}
