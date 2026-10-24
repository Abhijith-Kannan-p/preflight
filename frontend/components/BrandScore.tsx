"use client";

import { motion } from "framer-motion";

import { InfoTip } from "./ui";

const COLOR = (s: number) => (s >= 85 ? "#0F8B7E" : s >= 60 ? "#D98E1F" : "#C8463D");

/** Semicircle gauge from 0 to 100. */
export function BrandScoreGauge({ score, size = 168, pending = false }: { score: number | null; size?: number; pending?: boolean }) {
  const value = score ?? 0;
  const r = size / 2 - 12;
  const length = Math.PI * r;
  const shown = pending ? 0 : value / 100;
  return (
    <div className="flex flex-col items-center" data-tour="brand-score">
      <svg width={size} height={size / 2 + 14} viewBox={`0 0 ${size} ${size / 2 + 14}`} role="img" aria-label={pending ? "Brand Score pending" : `Brand Score ${value} out of 100`}>
        <path d={`M 12 ${size / 2} A ${r} ${r} 0 0 1 ${size - 12} ${size / 2}`} fill="none" stroke="#ECE4CF" strokeWidth="12" strokeLinecap="round" />
        <motion.path
          d={`M 12 ${size / 2} A ${r} ${r} 0 0 1 ${size - 12} ${size / 2}`}
          fill="none"
          stroke={COLOR(value)}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={length}
          initial={{ strokeDashoffset: length }}
          animate={{ strokeDashoffset: length * (1 - shown) }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        />
        <text x="50%" y={size / 2 - 4} textAnchor="middle" className="fill-navy text-4xl font-bold" style={{ fontSize: size / 4.4 }}>
          {pending ? "…" : value}
        </text>
      </svg>
      <span className="-mt-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-navy-500">
        Brand Score
        <InfoTip text="100 minus 25 per critical, 10 per major and 3 per minor open finding. Fixing, or disputing with a reason, raises it." />
      </span>
    </div>
  );
}

export function ScorePill({ score }: { score: number | null }) {
  if (score == null) return <span className="text-sm text-navy-300">—</span>;
  return (
    <span className="inline-flex min-w-10 justify-center rounded-lg px-2 py-0.5 text-sm font-bold text-white" style={{ backgroundColor: COLOR(score) }}>
      {score}
    </span>
  );
}
