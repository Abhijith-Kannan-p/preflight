"use client";

// Instrument-style dial: a thin 240° arc with tick marks and a mono readout. No rainbow donut.

import { InfoTip } from "./ui";

const START = 150; // degrees, measured clockwise from +x (SVG convention)
const SWEEP = 240;

function point(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arc(cx: number, cy: number, r: number, from: number, to: number) {
  const a = point(cx, cy, r, from);
  const b = point(cx, cy, r, to);
  const large = to - from > 180 ? 1 : 0;
  return `M ${a.x} ${a.y} A ${r} ${r} 0 ${large} 1 ${b.x} ${b.y}`;
}

const tone = (s: number) => (s >= 85 ? "rgb(var(--cleared))" : s >= 60 ? "rgb(var(--amber))" : "rgb(var(--signal))");

export function BrandScoreGauge({ score, size = 148, pending = false }: { score: number | null; size?: number; pending?: boolean }) {
  const value = Math.max(0, Math.min(100, score ?? 0));
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 10;
  const end = START + (SWEEP * value) / 100;
  const ticks = Array.from({ length: 11 }, (_, i) => START + (SWEEP * i) / 10);
  return (
    <div className="flex flex-col items-center" data-tour="brand-score">
      <svg width={size} height={size * 0.82} viewBox={`0 0 ${size} ${size * 0.82}`} role="img" aria-label={pending ? "Brand Score pending" : `Brand Score ${value} out of 100`}>
        <path d={arc(cx, cy, r, START, START + SWEEP)} fill="none" stroke="rgb(var(--rule))" strokeWidth="2" />
        {ticks.map((deg, i) => {
          const outer = point(cx, cy, r + 5, deg);
          const inner = point(cx, cy, r - (i % 5 === 0 ? 7 : 3), deg);
          return <line key={i} x1={outer.x} y1={outer.y} x2={inner.x} y2={inner.y} stroke="rgb(var(--graphite))" strokeWidth={i % 5 === 0 ? 1.25 : 0.75} />;
        })}
        {!pending && value > 0 && <path d={arc(cx, cy, r, START, end)} fill="none" stroke={tone(value)} strokeWidth="3" strokeLinecap="butt" />}
        {!pending && (() => {
          const tip = point(cx, cy, r - 12, end);
          return <line x1={cx} y1={cy} x2={tip.x} y2={tip.y} stroke="rgb(var(--ink))" strokeWidth="1.25" />;
        })()}
        <circle cx={cx} cy={cy} r="3" fill="rgb(var(--ink))" />
        <text x={cx} y={cy + size * 0.27} textAnchor="middle" className="fill-ink font-serif" style={{ fontSize: size / 4.3, fontWeight: 500 }}>
          {pending ? "––" : String(value).padStart(2, "0")}
        </text>
      </svg>
      <span className="label -mt-1 flex items-center gap-1">
        Brand Score
        <InfoTip text="100 minus 25 per critical, 10 per major and 3 per minor open finding. Fixing, or disputing with a reason, raises it." />
      </span>
    </div>
  );
}

export function ScorePill({ score }: { score: number | null }) {
  if (score == null) return <span className="font-mono text-sm text-graphite">––</span>;
  return (
    <span className="inline-flex min-w-[2.5rem] items-center gap-1.5 font-mono text-sm font-medium text-ink">
      <span className="h-2 w-2" style={{ background: tone(score) }} aria-hidden="true" />
      {String(score).padStart(2, "0")}
    </span>
  );
}
