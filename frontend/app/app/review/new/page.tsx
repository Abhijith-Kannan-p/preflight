"use client";

import { clsx } from "clsx";
import { FileText, Loader2, Plane, Upload, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Channel, Sample } from "@/lib/types";

const ACCEPT = ".docx,.pdf,.txt,.md";
const MAX_BYTES = 5 * 1024 * 1024;

function NewReviewForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { can } = useSession();
  const samples = useSWR<Sample[]>("/api/samples");
  const channels = useSWR<Channel[]>("/api/rulebook/channels");
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [channel, setChannel] = useState("linkedin");
  const [file, setFile] = useState<File | null>(null);
  const [sample, setSample] = useState<Sample | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const tour = params.get("tour") === "1";

  function pickSample(s: Sample) {
    setSample(s);
    setFile(null);
    setChannel(s.channel);
    setTitle(s.title);
    setContent(s.filename ? "" : s.content);
    setError(null);
  }

  useEffect(() => {
    const wanted = params.get("sample");
    const match = samples.data?.find((s) => s.id === wanted);
    if (match) pickSample(match);
  }, [params, samples.data]);

  function pickFile(f: File | undefined) {
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setError("Files must be 5 MB or smaller.");
      return;
    }
    setFile(f);
    setSample(null);
    setContent("");
    setTitle(f.name.replace(/\.[^.]+$/, ""));
    setError(null);
  }

  async function run() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("channel", channel);
    form.set("title", title);
    if (file) form.set("file", file);
    else if (sample?.filename) form.set("sample_id", sample.id);
    else form.set("content", content);
    try {
      const created = await api<{ id: string }>("/api/reviews", { method: "POST", body: form });
      router.push(`/app/review/${created.id}${tour ? "?tour=1" : ""}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the review.");
      setBusy(false);
    }
  }

  const fileLabel = file?.name ?? (sample?.filename ? sample.filename : null);
  const ready = Boolean(fileLabel || content.trim());

  if (!can("submit_content")) {
    return (
      <ErrorState message="Your current role cannot submit content. Switch to abhi1 (Creator) or abhi3 (Brand Manager) in the top right." />
    );
  }

  return (
    <div className="animate-fade-in">
      <PageHeader title="New review" subtitle="Paste a draft or upload a file. Preflight checks it against the PayWise rulebook and approved facts in about ten seconds." />

      <section aria-labelledby="samples" className="mb-6">
        <h2 id="samples" className="label">Start from a sample draft</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-tour="samples">
          {samples.data
            ? samples.data.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => pickSample(s)}
                  aria-pressed={sample?.id === s.id}
                  className={clsx("card p-4 text-left transition hover:-translate-y-0.5 hover:shadow-lift", sample?.id === s.id && "ring-2 ring-teal")}
                >
                  <span className="flex items-center justify-between">
                    <span className="font-semibold">{s.label}</span>
                    <span className="rounded-md bg-paper-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-navy-500">{s.format}</span>
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-navy-500">{s.description}</span>
                </button>
              ))
            : [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div
          className={clsx("card relative p-4 transition", dragging && "ring-2 ring-teal")}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pickFile(e.dataTransfer.files[0]);
          }}
        >
          {fileLabel ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
              <FileText className="h-10 w-10 text-teal" aria-hidden="true" />
              <p className="font-semibold">{fileLabel}</p>
              <p className="text-sm text-navy-500">Preflight will extract the text, keep paragraph positions and check every block.</p>
              <button
                type="button"
                className="btn-ghost py-1 text-xs"
                onClick={() => {
                  setFile(null);
                  setSample(null);
                }}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" /> Remove file
              </button>
            </div>
          ) : (
            <>
              <label htmlFor="draft" className="label">Draft text (plain text or Markdown)</label>
              <textarea
                id="draft"
                value={content}
                onChange={(e) => {
                  setContent(e.target.value);
                  setSample(null);
                }}
                rows={12}
                maxLength={20000}
                placeholder="Paste your post, email or press release here…"
                className="input min-h-64 resize-y font-[inherit] leading-relaxed"
              />
              <div className="mt-2 flex items-center justify-between text-xs text-navy-500">
                <button type="button" onClick={() => inputRef.current?.click()} className="inline-flex items-center gap-1 font-medium text-teal-700 hover:underline">
                  <Upload className="h-3.5 w-3.5" aria-hidden="true" /> Upload DOCX, PDF, TXT or MD (or drop it here)
                </button>
                <span>{content.length.toLocaleString()} / 20,000</span>
              </div>
            </>
          )}
          <input ref={inputRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />
        </div>

        <aside className="card flex flex-col gap-4 p-4">
          <div>
            <label htmlFor="title" className="label">Title</label>
            <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. October launch post" maxLength={200} />
          </div>
          <div>
            <label htmlFor="channel" className="label">Channel</label>
            <select id="channel" className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
              {channels.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-navy-500">Sets length, hashtag and subject-line limits, and whether readability applies.</p>
          </div>
          {error && <ErrorState message={error} />}
          <button type="button" onClick={run} disabled={!ready || busy} className="btn-teal mt-auto py-3 text-base" data-tour="run">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plane className="h-4 w-4" aria-hidden="true" />}
            {busy ? "Starting…" : "Run Preflight"}
          </button>
          {!ready && <p className="-mt-2 text-center text-xs text-navy-500">Pick a sample, paste text or upload a file.</p>}
        </aside>
      </div>
    </div>
  );
}

export default function NewReviewPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <NewReviewForm />
    </Suspense>
  );
}
