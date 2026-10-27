"use client";

// Rule and fact tags (`CLM-04 · p14`, `F-087 v2`) open the source in a side drawer, so a
// reviewer can read the governing text without leaving the draft.

import { clsx } from "clsx";
import { BookOpen, X } from "lucide-react";
import { createContext, useContext, useEffect, useState } from "react";
import useSWR from "swr";

import type { FactInfo, RuleInfo } from "@/lib/types";

import { Skeleton } from "../ui";

type Source = { kind: "rule" | "fact"; id: string };

const SourceContext = createContext<(source: Source) => void>(() => undefined);

export function SourceProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState<Source | null>(null);
  return (
    <SourceContext.Provider value={setOpen}>
      {children}
      <SourceDrawer source={open} onClose={() => setOpen(null)} />
    </SourceContext.Provider>
  );
}

const pageOf = (ref: string) => ref.match(/#p(\d+)/)?.[1];

export function RuleTag({ id, source, className }: { id: string; source?: string; className?: string }) {
  const open = useContext(SourceContext);
  const page = source ? pageOf(source) : undefined;
  return (
    <button type="button" className={clsx("tag hover:border-ink", className)} onClick={(e) => { e.stopPropagation(); open({ kind: "rule", id }); }} title="Open the rule's source">
      {id}
      {page && <span className="text-graphite">· p{page}</span>}
    </button>
  );
}

export function FactTag({ id, version, className }: { id: string; version?: number; className?: string }) {
  const open = useContext(SourceContext);
  return (
    <button type="button" className={clsx("tag hover:border-ink", className)} onClick={(e) => { e.stopPropagation(); open({ kind: "fact", id }); }} title="Open the approved fact">
      {id}
      {version != null && <span className="text-graphite">v{version}</span>}
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-3 border-b border-rule py-2 text-sm">
      <dt className="label mb-0 pt-0.5">{label}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  );
}

function SourceDrawer({ source, onClose }: { source: Source | null; onClose: () => void }) {
  const rules = useSWR<RuleInfo[]>(source?.kind === "rule" ? "/api/rulebook/rules" : null);
  const facts = useSWR<FactInfo[]>(source?.kind === "fact" ? "/api/rulebook/facts" : null);

  useEffect(() => {
    if (!source) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [source, onClose]);

  if (!source) return null;
  const rule = rules.data?.find((r) => r.code === source.id);
  const fact = facts.data?.find((f) => f.id === source.id);
  const loading = source.kind === "rule" ? !rules.data && !rules.error : !facts.data && !facts.error;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/20" onClick={onClose}>
      <aside role="dialog" aria-modal="true" aria-label={`Source for ${source.id}`} className="sheet h-full w-full max-w-md overflow-y-auto border-l border-rule p-6 animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3 border-b border-rule pb-3">
          <div>
            <p className="label flex items-center gap-1.5"><BookOpen className="h-3 w-3" aria-hidden="true" /> {source.kind === "rule" ? "Rulebook source" : "Approved fact"}</p>
            <h2 className="font-serif text-xl text-ink">{source.id}</h2>
          </div>
          <button type="button" className="btn-ghost p-1.5" onClick={onClose} aria-label="Close source panel">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {loading && <Skeleton className="h-40" />}
        {source.kind === "rule" && rule && (
          <>
            <p className="font-serif text-lg leading-snug text-ink">{rule.title}</p>
            <p className="mt-2 text-sm leading-relaxed text-graphite">{rule.description}</p>
            <dl className="mt-4 border-t border-rule">
              <Row label="Severity">{rule.severity}</Row>
              <Row label="Category">{rule.category}</Row>
              <Row label="Source">{rule.source_doc}{rule.source_page != null && `, page ${rule.source_page}`}</Row>
              <Row label="Version">v{rule.version} · {rule.status}</Row>
            </dl>
          </>
        )}
        {source.kind === "fact" && fact && (
          <>
            <blockquote className="border-l-2 border-ink pl-3 font-serif text-lg leading-snug text-ink">{fact.statement}</blockquote>
            <dl className="mt-4 border-t border-rule">
              <Row label="Status">{fact.is_current ? "Current" : fact.superseded_by ? `Superseded by ${fact.superseded_by}` : fact.status}</Row>
              <Row label="Valid">{fact.valid_from ?? "—"} to {fact.valid_until ?? "open"}</Row>
              <Row label="Source">{fact.source_doc}{fact.source_page != null && `, page ${fact.source_page}`}</Row>
              <Row label="Version">v{fact.version}</Row>
            </dl>
          </>
        )}
        {!loading && !(source.kind === "rule" ? rule : fact) && <p className="text-sm text-graphite">This {source.kind} is not in the current rulebook. It may have been retired since the review ran.</p>}
      </aside>
    </div>
  );
}
