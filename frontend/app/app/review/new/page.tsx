"use client";

import { clsx } from "clsx";
import { FileText, ImageIcon, Loader2, Plane, Upload, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { CoachPanel } from "@/components/CoachTips";
import { SourceProvider } from "@/components/review/SourcePanel";
import { ErrorState, NextStep, PageHeader, Skeleton } from "@/components/ui";
import { API_URL, ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Channel, Sample } from "@/lib/types";

const ACCEPT = ".docx,.pdf,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.webp";
const MAX_BYTES = 5 * 1024 * 1024;
const IMAGE_FORMATS = new Set(["png", "jpg", "jpeg", "webp"]);
const VISUAL_FORMATS = new Set([...IMAGE_FORMATS, "html"]);

const isImageName = (name: string) => IMAGE_FORMATS.has(name.split(".").pop()?.toLowerCase() ?? "");
const isVisualSample = (s: Sample) => VISUAL_FORMATS.has(s.format) || s.id.includes("scanned");

function SampleCard({ sample, selected, onPick }: { sample: Sample; selected: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={selected}
      className={clsx("flex flex-col border bg-sheet p-3 text-left transition-colors hover:border-ink", selected ? "border-ink shadow-sheet" : "border-rule")}
    >
      <span className="flex items-start justify-between gap-2">
        <span className="font-medium text-ink">{sample.label}</span>
        <span className="tag shrink-0 uppercase">{sample.format}</span>
      </span>
      <span className="mt-1 block text-xs leading-relaxed text-graphite">{sample.description}</span>
    </button>
  );
}

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
  const [altText, setAltText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const runKey = useRef("");
  const tour = params.get("tour") === "1";

  const textSamples = samples.data?.filter((s) => !isVisualSample(s)) ?? [];
  const visualSamples = samples.data?.filter(isVisualSample) ?? [];

  function pickSample(s: Sample) {
    setSample(s);
    setFile(null);
    setChannel(s.channel);
    setTitle(s.title);
    setContent(s.filename ? "" : s.content);
    // Image samples carry a suggested alt text (some deliberately weak, for ACC-03).
    setAltText(s.filename && IMAGE_FORMATS.has(s.format) ? s.content : "");
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
    setAltText("");
    setTitle(f.name.replace(/\.[^.]+$/, ""));
    setError(null);
  }

  useEffect(() => {
    runKey.current = `run:${Date.now()}:${Math.random().toString(36).slice(2)}`;
  }, [content, title, channel, file, sample, altText]);

  const imageChosen = file ? isImageName(file.name) : Boolean(sample && IMAGE_FORMATS.has(sample.format));
  const preview = useMemo(() => {
    if (file && isImageName(file.name)) return URL.createObjectURL(file);
    if (sample?.filename && IMAGE_FORMATS.has(sample.format)) return `${API_URL}/api/samples/${sample.id}/file`;
    return null;
  }, [file, sample]);
  useEffect(() => () => {
    if (preview?.startsWith("blob:")) URL.revokeObjectURL(preview);
  }, [preview]);

  async function run() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("channel", channel);
    form.set("title", title);
    if (file) form.set("file", file);
    else if (sample?.filename) form.set("sample_id", sample.id);
    else form.set("content", content);
    if (imageChosen) form.set("alt_text", altText);
    try {
      // One key per form state: pressing Run twice (or retrying) opens the same review.
      const created = await api<{ id: string }>("/api/reviews", { method: "POST", body: form, idempotencyKey: runKey.current });
      router.push(`/app/review/${created.id}${tour ? "?tour=1" : ""}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the review.");
      setBusy(false);
    }
  }

  const fileLabel = file?.name ?? (sample?.filename ? sample.filename : null);
  const ready = Boolean(fileLabel || content.trim());

  if (!can("submit_content")) {
    return <ErrorState message="Your current role cannot submit content. Switch to abhi1 (Creator) or abhi3 (Brand Manager) in the top right." />;
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Intake"
        title="New review"
        subtitle="Paste a draft or upload a file: text, Word, PDF (including scans), an HTML email or an image. Preflight checks it against the PayWise rulebook and approved facts."
      />

      <SourceProvider>
        <CoachPanel />
      </SourceProvider>

      <section aria-labelledby="samples" className="mb-8 space-y-5" data-tour="samples">
        <div>
          <h2 id="samples" className="label">Start from a sample draft</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {samples.data ? textSamples.map((s) => <SampleCard key={s.id} sample={s} selected={sample?.id === s.id} onPick={() => pickSample(s)} />) : [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
          </div>
        </div>
        {visualSamples.length > 0 && (
          <div>
            <h2 className="label">Or a visual: images, a scanned flyer, an HTML email</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {visualSamples.map((s) => (
                <SampleCard key={s.id} sample={s} selected={sample?.id === s.id} onPick={() => pickSample(s)} />
              ))}
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div
          className={clsx("sheet relative p-4 transition", dragging && "ring-2 ring-teal")}
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
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element -- a local preview or the sample file
                <img src={preview} alt={altText || "Preview of the chosen image"} className="max-h-56 max-w-full border border-rule object-contain" />
              ) : (
                <FileText className="h-10 w-10 text-teal" strokeWidth={1.5} aria-hidden="true" />
              )}
              <p className="font-medium">{fileLabel}</p>
              <p className="max-w-md text-sm text-graphite">
                {imageChosen
                  ? "Preflight reads the text in the image (OCR) and checks brand colours, contrast, the logo and your alt text, then checks the text like any draft."
                  : "Preflight extracts the text, keeps paragraph positions and checks every block. Scanned PDFs are read with OCR."}
              </p>
              <button
                type="button"
                className="btn-ghost py-1 text-xs"
                onClick={() => {
                  setFile(null);
                  setSample(null);
                  setAltText("");
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
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-graphite">
                <button type="button" onClick={() => inputRef.current?.click()} className="inline-flex items-center gap-1 font-medium text-teal-700 hover:underline">
                  <Upload className="h-3.5 w-3.5" aria-hidden="true" /> Upload DOCX, PDF, TXT, MD, HTML or an image (or drop it here)
                </button>
                <span className="font-mono">{content.length.toLocaleString()} / 20,000</span>
              </div>
            </>
          )}
          <input ref={inputRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />
        </div>

        <aside className="sheet flex flex-col gap-4 p-4">
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
            <p className="mt-1 text-xs text-graphite">Sets length, hashtag and subject-line limits, and whether readability applies.</p>
          </div>
          {imageChosen && (
            <div>
              <label htmlFor="alt" className="label flex items-center gap-1">
                <ImageIcon className="h-3 w-3" aria-hidden="true" /> Alt text for this image
              </label>
              <textarea id="alt" className="input" rows={3} maxLength={500} value={altText} onChange={(e) => setAltText(e.target.value)} placeholder="What does the image show and say?" />
              <p className="mt-1 text-xs text-graphite">Screen readers read this aloud. Preflight checks it (ACC-03): no file names, no &ldquo;image of&rdquo;, not empty.</p>
            </div>
          )}
          {error && <ErrorState message={error} />}
          <button type="button" onClick={run} disabled={!ready || busy} className="btn-teal mt-auto py-3 text-base" data-tour="run">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plane className="h-4 w-4" aria-hidden="true" />}
            {busy ? "Starting…" : "Run Preflight"}
          </button>
          {!ready && <NextStep>Pick a sample, paste text or upload a file.</NextStep>}
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
