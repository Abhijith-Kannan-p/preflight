"use client";

// The rubber stamp an approval leaves on the proof: who cleared it, when, and the first
// eight characters of the audit-chain hash that records it.

import { clsx } from "clsx";

import type { Clearance } from "@/lib/types";

export const stampTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).toUpperCase() + " UTC";

export function Stamp({ tone, title, lines, className }: { tone: "cleared" | "amber"; title: string; lines: string[]; className?: string }) {
  const colour = tone === "cleared" ? "border-cleared text-cleared" : "border-amber text-amber-700";
  return (
    <div className={clsx("inline-block -rotate-[8deg] animate-stamp select-none border-[3px] border-double px-4 py-2 text-center font-mono uppercase mix-blend-multiply", colour, className)}>
      <p className="text-[15px] font-medium tracking-[0.18em]">{title}</p>
      {lines.map((l) => (
        <p key={l} className="text-[10px] tracking-[0.12em] opacity-90">{l}</p>
      ))}
    </div>
  );
}

export function ClearanceStamp({ clearance, className }: { clearance: Clearance; className?: string }) {
  return (
    <div role="img" aria-label={`Cleared for publication by ${clearance.approver}, audit hash ${clearance.audit_hash.slice(0, 8)}`} className={clsx("flex flex-wrap items-center gap-4", className)}>
      <Stamp tone="cleared" title="Cleared for publication" lines={[`By ${clearance.approver} · ${stampTime(clearance.at)}`, `Audit ${clearance.audit_hash.slice(0, 8)}`]} />
      {clearance.overrides > 0 && <Stamp tone="amber" title="Override noted" lines={[`${clearance.overrides} critical finding${clearance.overrides === 1 ? "" : "s"} overridden with a reason`]} className="rotate-[4deg]" />}
    </div>
  );
}
