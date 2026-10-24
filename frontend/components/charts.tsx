"use client";

// Chart building blocks. Palette validated with the dataviz validator against the paper
// surface (#FFFDF7): purple #6B4FA0 + teal #12A594 pass lightness, chroma, CVD (ΔE 18.9)
// and normal-vision (ΔE 25.5) checks. Text always uses ink colours, never series colours.

import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const SERIES = { first: "#6B4FA0", final: "#12A594" } as const;
const INK = "#1B2A4A";
const MUTED = "#4A5A7C";
const GRID = "#ECE4CF";

const tooltipStyle = {
  contentStyle: { background: "#FFFDF7", border: `1px solid ${GRID}`, borderRadius: 12, fontSize: 12, color: INK },
  labelStyle: { color: INK, fontWeight: 600 },
  itemStyle: { color: INK },
};

/** Horizontal bars for one measure across categories (one hue, values labelled). */
export function HBar({ data, label, value, unit = "", height }: { data: Record<string, string | number>[]; label: string; value: string; unit?: string; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(120, data.length * 34 + 20)}>
      <BarChart data={data} layout="vertical" margin={{ left: 4, right: 36, top: 4, bottom: 4 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={unit !== ""} />
        <YAxis type="category" dataKey={label} width={170} tick={{ fill: INK, fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(27,42,74,0.05)" }} formatter={(v: number) => [`${v}${unit}`, ""]} separator="" />
        <Bar isAnimationActive={false} dataKey={value} fill={SERIES.final} radius={[0, 4, 4, 0]} maxBarSize={22} label={{ position: "right", fill: INK, fontSize: 11, formatter: (v: number) => `${v}${unit}` }} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Brand Score over time: first drafts vs the version that was approved (one 0-100 axis). */
export function ScoreTrend({ data }: { data: { date: string; first: number; final: number }[] }) {
  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-navy-500" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: SERIES.first }} /> First draft</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: SERIES.final }} /> After fixes</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: -16, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="date" tick={{ fill: MUTED, fontSize: 11 }} tickFormatter={(d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short" })} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 100]} tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip {...tooltipStyle} labelFormatter={(d: string) => new Date(d).toLocaleDateString(undefined, { dateStyle: "medium" })} />
          <Line isAnimationActive={false} type="linear" dataKey="first" name="First draft" stroke={SERIES.first} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "#FFFDF7" }} activeDot={{ r: 5 }} />
          <Line isAnimationActive={false} type="linear" dataKey="final" name="After fixes" stroke={SERIES.final} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "#FFFDF7" }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
