// Connectors from proof marks to their margin notes, one orthogonal elbow per note: from the
// mark (down into the line spacing for text), right to a lane in the gutter between the sheet
// and the notes, along the lane to the note's level, then into the note's number badge.
//
// Lanes follow reading order, the first note taking the lane nearest the notes. On the text
// proof notes sit at or below their marks, so no connector's horizontal crosses another's
// vertical; where most notes sit above their marks (a short note list beside a tall image) the
// order flips for the same reason. The horizontals into the notes start right of every lane,
// so no line passes over a note.

import { clsx } from "clsx";

export interface ConnectorSpec {
  id: string;
  colour: string;
  /** Where the line leaves the mark, relative to the desk. */
  start: { x: number; y: number };
  /** For text: the y of the line-spacing row the line runs along to leave the sheet. */
  via?: number;
  /** The note's number badge, relative to the desk. */
  end: { x: number; y: number };
}

export interface ConnectorPath {
  id: string;
  d: string;
  colour: string;
  start: { x: number; y: number };
}

const EDGE = 6; // clear space between the outermost lanes and the sheet / the notes
const MAX_SPACING = 6;

export function routeConnectors(specs: ConnectorSpec[], gutter: { left: number; right: number }): ConnectorPath[] {
  const room = Math.max(0, gutter.right - gutter.left - EDGE * 2);
  const spacing = specs.length > 1 ? Math.min(MAX_SPACING, room / (specs.length - 1)) : 0;
  const rising = specs.filter((s) => s.end.y < (s.via ?? s.start.y)).length > specs.length / 2;
  return specs.map((s, i) => {
    const lane = gutter.right - EDGE - (rising ? specs.length - 1 - i : i) * spacing;
    const r = (n: number) => Math.round(n * 2) / 2;
    const parts = [`M ${r(s.start.x)} ${r(s.start.y)}`];
    if (s.via != null) parts.push(`V ${r(s.via)}`);
    parts.push(`H ${r(lane)}`, `V ${r(s.end.y)}`, `H ${r(s.end.x)}`);
    return { id: s.id, d: parts.join(" "), colour: s.colour, start: s.start };
  });
}

/** Every connector at about a third strength; the active one full strength and 2 px, on top. */
export function ConnectorLayer({ paths, active }: { paths: ConnectorPath[]; active: string | null }) {
  if (!paths.length) return null;
  const ordered = [...paths.filter((p) => p.id !== active), ...paths.filter((p) => p.id === active)];
  return (
    <svg className="pointer-events-none absolute inset-0 hidden h-full w-full overflow-visible lg:block" aria-hidden="true" data-connectors={paths.length}>
      {ordered.map((p) => {
        const on = p.id === active;
        return (
          <g key={p.id} data-connector={p.id} className={clsx("transition-opacity duration-150", on ? "opacity-100" : "opacity-[0.35]")}>
            <path d={p.d} stroke={p.colour} strokeWidth={on ? 2 : 1} fill="none" strokeLinejoin="round" />
            <circle cx={p.start.x} cy={p.start.y} r={on ? 2.5 : 1.5} fill={p.colour} />
          </g>
        );
      })}
    </svg>
  );
}
