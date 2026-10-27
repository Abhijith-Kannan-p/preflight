"use client";

import { clsx } from "clsx";
import { ArrowRight, Download, History, Lock, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import useSWR from "swr";

import { Chip, ComingInRound3, ErrorState, Modal, PageHeader, Skeleton } from "@/components/ui";
import { API_URL, ApiError, api } from "@/lib/api";
import { SEVERITY_STYLE } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Channel, Severity } from "@/lib/types";

interface Rule {
  code: string;
  category: string;
  title: string;
  description: string;
  severity: Severity;
  config: Record<string, unknown>;
  source_doc: string;
  source_page: number | null;
  source_ref: string;
  version: number;
  status: string;
  created_by: string | null;
  approved_by: string | null;
}

interface Fact {
  id: string;
  statement: string;
  source_doc: string;
  source_page: number | null;
  source_ref: string;
  valid_from: string | null;
  valid_until: string | null;
  superseded_by: string | null;
  version: number;
  status: string;
  is_current: boolean;
}

interface Term {
  id: number;
  term: string;
  kind: "product_name" | "banned" | "discouraged";
  variants: string[];
  replacement: string | null;
  case_sensitive: boolean;
  rule_code: string;
  note: string;
}

interface Confidential {
  id: number;
  term: string;
  kind: string;
  note: string;
}

const TABS = ["Rules", "Approved facts", "Terminology", "Channels", "Confidential terms"] as const;
type Tab = (typeof TABS)[number];

async function send(path: string, method: string, body?: unknown) {
  return api(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

function CsvTools({ kind, canEdit, onImported }: { kind: "rules" | "facts" | "terms"; canEdit: boolean; onImported: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  async function upload(file: File | undefined) {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    try {
      const r = await api<{ created: number; updated: number; unchanged: number; errors: string[] }>(`/api/rulebook/import/${kind}`, { method: "POST", body: form });
      setMessage(`Imported: ${r.created} new, ${r.updated} updated, ${r.unchanged} unchanged${r.errors.length ? `. ${r.errors.length} row(s) skipped: ${r.errors[0]}` : "."}`);
      onImported();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Import failed.");
    }
    if (input.current) input.current.value = "";
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <a href={`${API_URL}/api/rulebook/export/${kind}.csv`} className="btn-ghost py-1.5 text-xs">
        <Download className="h-3.5 w-3.5" aria-hidden="true" /> Export CSV
      </a>
      {canEdit && (
        <>
          <button type="button" className="btn-ghost py-1.5 text-xs" onClick={() => input.current?.click()}>
            <Upload className="h-3.5 w-3.5" aria-hidden="true" /> Import CSV
          </button>
          <input ref={input} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
        </>
      )}
      {message && <span className="text-xs text-navy-500">{message}</span>}
    </div>
  );
}

// --- Rules ------------------------------------------------------------------------------

function RuleForm({ rule, onDone }: { rule: Rule | null; onDone: () => void }) {
  const [form, setForm] = useState({
    code: rule?.code ?? "",
    category: rule?.category ?? "claims",
    title: rule?.title ?? "",
    description: rule?.description ?? "",
    severity: rule?.severity ?? "major",
    config: JSON.stringify(rule?.config ?? {}, null, 1),
    source_doc: rule?.source_doc ?? "brand_book.pdf",
    source_page: rule?.source_page?.toString() ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  async function save() {
    setError(null);
    let config: unknown;
    try {
      config = JSON.parse(form.config || "{}");
    } catch {
      setError("Config must be valid JSON.");
      return;
    }
    const body = { ...form, config, source_page: form.source_page ? Number(form.source_page) : null };
    try {
      if (rule) await send(`/api/rulebook/rules/${rule.code}`, "PUT", body);
      else await send("/api/rulebook/rules", "POST", body);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the rule.");
    }
  }

  return (
    <div className="grid gap-3 text-sm sm:grid-cols-2">
      {!rule && (
        <>
          <label className="block">
            <span className="label">Rule ID</span>
            <input className="input" value={form.code} onChange={set("code")} placeholder="CLM-09" />
          </label>
          <label className="block">
            <span className="label">Category</span>
            <select className="input" value={form.category} onChange={set("category")}>
              {["claims", "terminology", "tone", "disclaimer", "channel", "readability"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </>
      )}
      <label className="block sm:col-span-2">
        <span className="label">Title</span>
        <input className="input" value={form.title} onChange={set("title")} />
      </label>
      <label className="block sm:col-span-2">
        <span className="label">Description</span>
        <textarea className="input" rows={3} value={form.description} onChange={set("description")} />
      </label>
      <label className="block">
        <span className="label">Severity</span>
        <select className="input" value={form.severity} onChange={set("severity")}>
          <option value="critical">Critical (blocks approval)</option>
          <option value="major">Major</option>
          <option value="minor">Minor</option>
        </select>
      </label>
      <div className="grid grid-cols-[1fr_80px] gap-2">
        <label className="block">
          <span className="label">Source document</span>
          <input className="input" value={form.source_doc} onChange={set("source_doc")} />
        </label>
        <label className="block">
          <span className="label">Page</span>
          <input className="input" type="number" min={1} value={form.source_page} onChange={set("source_page")} />
        </label>
      </div>
      <label className="block sm:col-span-2">
        <span className="label">Config (JSON: patterns, disclaimer, thresholds, fallback wording)</span>
        <textarea className="input font-mono text-xs" rows={4} value={form.config} onChange={set("config")} />
      </label>
      {rule && <p className="text-xs text-navy-500 sm:col-span-2">Saving creates version {rule.version + 1}; version {rule.version} is kept in history.</p>}
      {error && <div className="sm:col-span-2"><ErrorState message={error} /></div>}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <button type="button" className="btn-primary" onClick={save}>{rule ? "Save new version" : "Create rule"}</button>
      </div>
    </div>
  );
}

function RulesTab({ canEdit }: { canEdit: boolean }) {
  const { data, error, mutate } = useSWR<Rule[]>("/api/rulebook/rules");
  const [editing, setEditing] = useState<Rule | null | "new">(null);
  const [history, setHistory] = useState<string | null>(null);
  const versions = useSWR<Rule[]>(history ? `/api/rulebook/rules/${history}/versions` : null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <CsvTools kind="rules" canEdit={canEdit} onImported={() => mutate()} />
        {canEdit && <button type="button" className="btn-teal py-1.5 text-xs" onClick={() => setEditing("new")}><Plus className="h-3.5 w-3.5" aria-hidden="true" /> New rule</button>}
      </div>
      <div className="overflow-hidden rounded-2xl border border-paper-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper-100 text-xs uppercase tracking-wide text-navy-500">
            <tr>
              <th className="px-3 py-2">Rule</th>
              <th className="px-3 py-2">Severity</th>
              <th className="hidden px-3 py-2 md:table-cell">Source</th>
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-paper-200 bg-paper-50">
            {data.map((r) => (
              <tr key={`${r.code}-${r.version}`} className="align-top">
                <td className="px-3 py-3">
                  <p className="font-semibold"><span className="font-mono text-xs">{r.code}</span> · {r.title}</p>
                  <p className="mt-0.5 text-xs text-navy-500">{r.description}</p>
                </td>
                <td className="px-3 py-3"><Chip className={SEVERITY_STYLE[r.severity].chip}>{SEVERITY_STYLE[r.severity].label}</Chip></td>
                <td className="hidden px-3 py-3 font-mono text-xs text-navy-500 md:table-cell">{r.source_ref.replace("#p", " p")}</td>
                <td className="px-3 py-3 text-xs">
                  v{r.version}
                  {r.version > 1 && (
                    <button type="button" className="ml-1 text-teal-700 hover:underline" onClick={() => setHistory(r.code)}>
                      <History className="inline h-3 w-3" aria-label="Version history" />
                    </button>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right">
                  {canEdit && (
                    <>
                      <button type="button" aria-label={`Edit ${r.code}`} className="rounded-lg p-1.5 text-navy-500 hover:bg-paper-100" onClick={() => setEditing(r)}><Pencil className="h-3.5 w-3.5" /></button>
                      <button
                        type="button"
                        aria-label={`Retire ${r.code}`}
                        className="rounded-lg p-1.5 text-navy-500 hover:bg-danger-50 hover:text-danger"
                        onClick={async () => {
                          if (window.confirm(`Retire ${r.code}? It stops applying to new reviews and stays in history.`)) {
                            await send(`/api/rulebook/rules/${r.code}`, "DELETE");
                            void mutate();
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Modal open={editing !== null} title={editing === "new" ? "New rule" : `Edit ${editing?.code ?? ""}`} onClose={() => setEditing(null)}>
        {editing !== null && <RuleForm rule={editing === "new" ? null : editing} onDone={() => { setEditing(null); void mutate(); }} />}
      </Modal>
      <Modal open={history !== null} title={`Version history · ${history}`} onClose={() => setHistory(null)}>
        <ol className="space-y-3 text-sm">
          {versions.data?.map((v) => (
            <li key={v.version} className="rounded-xl bg-paper-100 p-3">
              <p className="font-semibold">v{v.version} · {v.status} · {SEVERITY_STYLE[v.severity].label}</p>
              <p className="text-navy-500">{v.title}: {v.description}</p>
            </li>
          ))}
        </ol>
      </Modal>
    </div>
  );
}

// --- Facts ------------------------------------------------------------------------------

const TIMELINE_START = new Date("2025-01-01").getTime();
const TIMELINE_END = new Date("2027-01-01").getTime();
const pos = (iso: string | null, fallback: number) => {
  const t = iso ? new Date(iso).getTime() : fallback;
  return Math.min(100, Math.max(0, ((t - TIMELINE_START) / (TIMELINE_END - TIMELINE_START)) * 100));
};

function FactForm({ fact, mode, onDone }: { fact: Fact | null; mode: "new" | "edit" | "supersede"; onDone: () => void }) {
  const [form, setForm] = useState({
    id: mode === "new" ? "" : fact?.id ?? "",
    new_id: "",
    statement: mode === "supersede" ? "" : fact?.statement ?? "",
    source_doc: fact?.source_doc ?? "",
    source_page: fact?.source_page?.toString() ?? "",
    valid_from: mode === "supersede" ? new Date().toISOString().slice(0, 10) : fact?.valid_from ?? "",
    valid_until: mode === "supersede" ? "" : fact?.valid_until ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  async function save() {
    setError(null);
    const common = { statement: form.statement, source_doc: form.source_doc, source_page: form.source_page ? Number(form.source_page) : null };
    try {
      if (mode === "new") await send("/api/rulebook/facts", "POST", { ...common, id: form.id, valid_from: form.valid_from || null, valid_until: form.valid_until || null });
      if (mode === "edit" && fact) await send(`/api/rulebook/facts/${fact.id}`, "PUT", { ...common, valid_from: form.valid_from || null, valid_until: form.valid_until || null });
      if (mode === "supersede" && fact) await send(`/api/rulebook/facts/${fact.id}/supersede`, "POST", { ...common, new_id: form.new_id, valid_from: form.valid_from });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the fact.");
    }
  }
  return (
    <div className="grid gap-3 text-sm sm:grid-cols-2">
      {mode === "supersede" && fact && (
        <p className="rounded-xl bg-amber-50 p-3 text-amber-700 sm:col-span-2">
          {fact.id} “{fact.statement}” ends the day before the new fact starts. Drafts that still use the old wording are flagged as outdated (CLM-03) and pointed at the new fact.
        </p>
      )}
      {(mode === "new" || mode === "supersede") && (
        <label className="block">
          <span className="label">{mode === "new" ? "Fact ID" : "New fact ID"}</span>
          <input className="input" value={mode === "new" ? form.id : form.new_id} onChange={set(mode === "new" ? "id" : "new_id")} placeholder="F-401" />
        </label>
      )}
      <label className="block sm:col-span-2">
        <span className="label">Statement (as it may be quoted)</span>
        <textarea className="input" rows={2} value={form.statement} onChange={set("statement")} />
      </label>
      <label className="block">
        <span className="label">Source document</span>
        <input className="input" value={form.source_doc} onChange={set("source_doc")} />
      </label>
      <label className="block">
        <span className="label">Page</span>
        <input className="input" type="number" min={1} value={form.source_page} onChange={set("source_page")} />
      </label>
      <label className="block">
        <span className="label">Valid from</span>
        <input className="input" type="date" value={form.valid_from} onChange={set("valid_from")} />
      </label>
      {mode !== "supersede" && (
        <label className="block">
          <span className="label">Valid until (optional)</span>
          <input className="input" type="date" value={form.valid_until} onChange={set("valid_until")} />
        </label>
      )}
      {error && <div className="sm:col-span-2"><ErrorState message={error} /></div>}
      <div className="flex justify-end sm:col-span-2">
        <button type="button" className="btn-primary" onClick={save}>{mode === "supersede" ? "Supersede fact" : "Save fact"}</button>
      </div>
    </div>
  );
}

function FactsTab({ canEdit }: { canEdit: boolean }) {
  const { data, error, mutate } = useSWR<Fact[]>("/api/rulebook/facts");
  const [dialog, setDialog] = useState<{ fact: Fact | null; mode: "new" | "edit" | "supersede" } | null>(null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  const today = pos(new Date().toISOString(), 0);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <CsvTools kind="facts" canEdit={canEdit} onImported={() => mutate()} />
        {canEdit && <button type="button" className="btn-teal py-1.5 text-xs" onClick={() => setDialog({ fact: null, mode: "new" })}><Plus className="h-3.5 w-3.5" aria-hidden="true" /> New fact</button>}
      </div>
      <p className="mb-3 text-xs text-navy-500">The bar shows when each fact is valid (2025 to 2026). The navy line is today. Superseded facts stay listed so outdated claims can be recognised.</p>
      <ul className="divide-y divide-paper-200 overflow-hidden rounded-2xl border border-paper-200 bg-paper-50">
        {data.map((f) => (
          <li key={f.id} className={clsx("grid gap-3 px-4 py-3 md:grid-cols-[1fr_240px_auto]", !f.is_current && "bg-paper-100/60")}>
            <div>
              <p className="text-sm">
                <span className="font-mono text-xs font-semibold">{f.id}</span>{" "}
                {f.is_current ? <Chip className="bg-teal-50 text-teal-700 ring-teal/30">Current</Chip> : <Chip className="bg-paper-100 text-navy-500 ring-paper-200">{f.superseded_by ? "Superseded" : "Not valid today"}</Chip>}{" "}
                {f.statement}
              </p>
              <p className="mt-0.5 text-xs text-navy-500">
                {f.source_ref.replace("#p", " p")} · v{f.version}
                {f.superseded_by && (
                  <span className="ml-1 inline-flex items-center gap-1 font-medium text-amber-700">
                    {f.id} <ArrowRight className="h-3 w-3" aria-hidden="true" /> {f.superseded_by}
                  </span>
                )}
              </p>
            </div>
            <div className="relative mt-1 h-3 self-center rounded-none bg-paper-100" aria-label={`Valid ${f.valid_from ?? "always"} to ${f.valid_until ?? "open-ended"}`}>
              <span className={clsx("absolute inset-y-0 rounded-none", f.is_current ? "bg-teal" : "bg-navy-300")} style={{ left: `${pos(f.valid_from, TIMELINE_START)}%`, right: `${100 - pos(f.valid_until, TIMELINE_END)}%` }} />
              <span className="absolute -top-1 h-5 w-0.5 bg-navy" style={{ left: `${today}%` }} />
            </div>
            <div className="flex items-center justify-end gap-1">
              {canEdit && f.status === "active" && (
                <>
                  <button type="button" aria-label={`Edit ${f.id}`} className="rounded-lg p-1.5 text-navy-500 hover:bg-paper-100" onClick={() => setDialog({ fact: f, mode: "edit" })}><Pencil className="h-3.5 w-3.5" /></button>
                  {!f.superseded_by && (
                    <button type="button" className="btn-ghost py-1 text-xs" onClick={() => setDialog({ fact: f, mode: "supersede" })}>Supersede</button>
                  )}
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      <Modal open={dialog !== null} title={dialog?.mode === "new" ? "New approved fact" : dialog?.mode === "supersede" ? `Supersede ${dialog.fact?.id}` : `Edit ${dialog?.fact?.id}`} onClose={() => setDialog(null)}>
        {dialog && <FactForm fact={dialog.fact} mode={dialog.mode} onDone={() => { setDialog(null); void mutate(); }} />}
      </Modal>
    </div>
  );
}

// --- Terms, channels, confidential ------------------------------------------------------

const KIND_LABEL: Record<Term["kind"], string> = { product_name: "Product name", banned: "Banned", discouraged: "Discouraged" };

function TermsTab({ canEdit }: { canEdit: boolean }) {
  const { data, error, mutate } = useSWR<Term[]>("/api/rulebook/terms");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ term: "", kind: "banned", variants: "", replacement: "", case_sensitive: false, rule_code: "TRM-05", note: "" });
  const [formError, setFormError] = useState<string | null>(null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-96" />;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <CsvTools kind="terms" canEdit={canEdit} onImported={() => mutate()} />
        {canEdit && <button type="button" className="btn-teal py-1.5 text-xs" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" aria-hidden="true" /> New term</button>}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {data.map((t) => (
          <div key={t.id} className="card p-4 text-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold">{t.term}</p>
              <div className="flex items-center gap-1">
                <Chip className={t.kind === "banned" ? "bg-danger-50 text-danger-700 ring-danger/30" : t.kind === "discouraged" ? "bg-amber-50 text-amber-700 ring-amber/30" : "bg-teal-50 text-teal-700 ring-teal/30"}>{KIND_LABEL[t.kind]}</Chip>
                {canEdit && (
                  <button type="button" aria-label={`Delete ${t.term}`} className="rounded-lg p-1 text-navy-500 hover:bg-danger-50 hover:text-danger" onClick={async () => { await send(`/api/rulebook/terms/${t.id}`, "DELETE"); void mutate(); }}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
            {t.variants.length > 0 && <p className="mt-1 text-xs text-navy-500">Catches: {t.variants.join(", ")}{t.case_sensitive ? " (case-sensitive, plus fuzzy near-misses)" : ""}</p>}
            {t.replacement && <p className="mt-1 text-xs">Suggest: <strong>{t.replacement}</strong></p>}
            <p className="mt-1 text-xs text-navy-500"><span className="font-mono">{t.rule_code}</span> · {t.note}</p>
          </div>
        ))}
      </div>
      <Modal open={open} title="New term" onClose={() => setOpen(false)}>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <label className="block"><span className="label">Term</span><input className="input" value={form.term} onChange={(e) => setForm({ ...form, term: e.target.value })} /></label>
          <label className="block"><span className="label">Kind</span>
            <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value, rule_code: e.target.value === "product_name" ? "TRM-02" : "TRM-05" })}>
              <option value="banned">Banned</option><option value="discouraged">Discouraged</option><option value="product_name">Product name</option>
            </select>
          </label>
          <label className="block sm:col-span-2"><span className="label">Wrong forms to catch (comma-separated)</span><input className="input" value={form.variants} onChange={(e) => setForm({ ...form, variants: e.target.value })} /></label>
          <label className="block"><span className="label">Suggested replacement</span><input className="input" value={form.replacement} onChange={(e) => setForm({ ...form, replacement: e.target.value })} /></label>
          <label className="block"><span className="label">Note</span><input className="input" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
          {formError && <div className="sm:col-span-2"><ErrorState message={formError} /></div>}
          <div className="flex justify-end sm:col-span-2">
            <button type="button" className="btn-primary" onClick={async () => {
              try {
                await send("/api/rulebook/terms", "POST", { ...form, variants: form.variants.split(",").map((v) => v.trim()).filter(Boolean), replacement: form.replacement || null, case_sensitive: form.kind === "product_name" });
                setOpen(false);
                void mutate();
              } catch (e) {
                setFormError(e instanceof Error ? e.message : "Could not save.");
              }
            }}>Add term</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function ChannelsTab({ canEdit }: { canEdit: boolean }) {
  const { data, error, mutate } = useSWR<Channel[]>("/api/rulebook/channels");
  const [saved, setSaved] = useState<string | null>(null);
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-64" />;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {data.map((c) => (
        <form
          key={c.id}
          className="card space-y-3 p-4 text-sm"
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            const num = (k: string) => (f.get(k) ? Number(f.get(k)) : null);
            await send(`/api/rulebook/channels/${c.id}`, "PUT", { max_chars: num("max_chars"), max_hashtags: num("max_hashtags"), subject_max_chars: num("subject_max_chars"), consumer: f.get("consumer") === "on" });
            setSaved(c.id);
            void mutate();
          }}
        >
          <div className="flex items-center justify-between">
            <p className="font-semibold">{c.name}</p>
            {c.rule_code && <span className="font-mono text-xs text-navy-500">{c.rule_code}</span>}
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[["max_chars", "Max characters", c.max_chars], ["max_hashtags", "Max hashtags", c.max_hashtags], ["subject_max_chars", "Subject max", c.subject_max_chars]].map(([name, label, value]) => (
              <label key={name as string} className="block">
                <span className="label">{label}</span>
                <input name={name as string} type="number" min={0} className="input" defaultValue={(value as number | null) ?? ""} disabled={!canEdit} placeholder="none" />
              </label>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input name="consumer" type="checkbox" defaultChecked={c.consumer} disabled={!canEdit} /> Consumer channel (readability RDB-01 applies)
          </label>
          {canEdit && (
            <div className="flex items-center justify-end gap-2">
              {saved === c.id && <span className="text-xs text-teal-700">Saved</span>}
              <button type="submit" className="btn-ghost py-1 text-xs">Save</button>
            </div>
          )}
        </form>
      ))}
    </div>
  );
}

function ConfidentialTab({ canEdit }: { canEdit: boolean }) {
  const { data, error, mutate } = useSWR<Confidential[]>("/api/rulebook/confidential");
  const [term, setTerm] = useState("");
  if (error) return <ErrorState message={error.message} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 rounded-xl bg-paper-100 p-3 text-sm text-navy-500">
        <Lock className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden="true" />
        These terms are replaced with tokens such as [CONFIDENTIAL_1] before any text is sent to a hosted LLM, then restored in the results. Emails, phone numbers and ₹ amounts are masked automatically.
      </p>
      <ul className="divide-y divide-paper-200 overflow-hidden rounded-2xl border border-paper-200 bg-paper-50">
        {data.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
            <span>
              <span className="font-semibold">{c.term}</span> <span className="text-xs text-navy-500">· {c.kind} · {c.note}</span>
            </span>
            {canEdit && (
              <button type="button" aria-label={`Remove ${c.term}`} className="rounded-lg p-1 text-navy-500 hover:bg-danger-50 hover:text-danger" onClick={async () => { await send(`/api/rulebook/confidential/${c.id}`, "DELETE"); void mutate(); }}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="flex gap-2">
          <input className="input" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Add a confidential term, e.g. an unreleased product name" />
          <button type="button" className="btn-teal" disabled={term.trim().length < 2} onClick={async () => { await send("/api/rulebook/confidential", "POST", { term, kind: "project" }); setTerm(""); void mutate(); }}>Add</button>
        </div>
      )}
    </div>
  );
}

export default function RulebookPage() {
  const { can } = useSession();
  const canEdit = can("edit_rulebook");
  const [tab, setTab] = useState<Tab>("Rules");
  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Rulebook"
        subtitle="The PayWise Brand Knowledge Base: versioned rules with their source pages, approved facts with validity dates, terminology, channel limits and confidential terms. Every finding Preflight raises cites an entry here."
      />
      {!canEdit && (
        <p className="mb-4 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">Read-only for your role. Switch to abhi3 (Brand Manager) in the top right to edit rules and facts.</p>
      )}
      <div className="mb-5">
        <ComingInRound3 title="Upload your brand book PDF and Preflight drafts the rules" text="The Rulebook Compiler will extract typed rules with page references for a brand manager to approve, and learn a Voice Fingerprint from approved content." />
      </div>
      <div role="tablist" aria-label="Rulebook sections" className="mb-4 flex gap-1 overflow-x-auto rounded-xl bg-paper-100 p-1">
        {TABS.map((t) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)} className={clsx("whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium", tab === t ? "bg-paper-50 text-navy shadow-card" : "text-navy-500 hover:text-navy")}>
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "Rules" && <RulesTab canEdit={canEdit} />}
        {tab === "Approved facts" && <FactsTab canEdit={canEdit} />}
        {tab === "Terminology" && <TermsTab canEdit={canEdit} />}
        {tab === "Channels" && <ChannelsTab canEdit={canEdit} />}
        {tab === "Confidential terms" && <ConfidentialTab canEdit={canEdit} />}
      </div>
    </div>
  );
}
