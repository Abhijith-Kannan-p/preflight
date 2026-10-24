import { BookCheck, FileSearch, Scale, ShieldCheck, Sparkles, UserCheck } from "lucide-react";
import Link from "next/link";

import { Footer } from "@/components/Footer";
import { Logo } from "@/components/Logo";
import { Splash } from "@/components/Splash";
import { TunnelHero } from "@/components/TunnelHero";
import { API_URL, GITHUB_URL } from "@/lib/api";

const PRINCIPLES = [
  { icon: BookCheck, name: "Grounded", text: "Every finding cites a brand rule (with page) or an approved fact. The validator rejects anything else." },
  { icon: FileSearch, name: "Explainable", text: "Plain-language reasons, evidence quotes, confidence and the exact steps behind each claim verdict." },
  { icon: UserCheck, name: "Human-controlled", text: "AI suggests; it never approves or edits on its own. Every decision is signed into a hash-chained audit log." },
];

const STEPS = [
  { n: "1", title: "Paste or upload", text: "Text, Markdown, DOCX or PDF. Pick the channel: LinkedIn, X, email, press release." },
  { n: "2", title: "Preflight checks", text: "Terminology, disclaimers, channel limits, readability, tone, and the Claim Ledger, all running at once." },
  { n: "3", title: "Fix with suggestions", text: "Accept, edit, dispute or escalate each finding. Re-check and watch the Brand Score rise." },
  { n: "4", title: "Approve with a receipt", text: "Critical findings block approval. The approver signs off and a Review Receipt records it all." },
];

export default function Landing() {
  return (
    <>
      <Splash />
      <header className="fixed inset-x-0 top-0 z-40 border-b border-paper-200/70 bg-paper/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Logo />
          <nav className="flex items-center gap-4 text-sm font-medium">
            <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="hidden text-navy-500 hover:text-navy sm:inline">For developers</a>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hidden text-navy-500 hover:text-navy sm:inline">GitHub</a>
            <Link href="/app" className="btn-primary py-1.5">Open the app</Link>
          </nav>
        </div>
      </header>

      <main>
        <TunnelHero />

        <section className="mx-auto max-w-6xl px-6 py-20" aria-labelledby="principles">
          <h2 id="principles" className="text-center text-sm font-semibold uppercase tracking-[0.3em] text-teal-700">Three principles</h2>
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            {PRINCIPLES.map(({ icon: Icon, name, text }) => (
              <div key={name} className="card p-6">
                <Icon className="h-6 w-6 text-teal" aria-hidden="true" />
                <h3 className="mt-4 text-lg font-semibold">{name}</h3>
                <p className="mt-2 text-sm leading-relaxed text-navy-500">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-8" aria-labelledby="how">
          <div className="rounded-3xl border-2 border-paper-200 bg-paper-50 p-8 shadow-card sm:p-12">
            <h2 id="how" className="text-3xl font-bold tracking-tight">How it works</h2>
            <ol className="mt-10 grid gap-6 md:grid-cols-4">
              {STEPS.map((s) => (
                <li key={s.n} className="relative">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-navy text-sm font-bold text-paper-50">{s.n}</span>
                  <h3 className="mt-4 font-semibold">{s.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-navy-500">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-20" aria-labelledby="example">
          <div className="grid items-center gap-10 md:grid-cols-2">
            <div>
              <h2 id="example" className="text-3xl font-bold tracking-tight">One LinkedIn post, six problems</h2>
              <p className="mt-3 text-navy-500">
                A superlative nobody can prove, an absolute security claim, a settlement time that changed on 2 Sep, a misspelt product name and two tone issues. Preflight catches all of them, explains each with its source, and proposes minimal fixes.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link href="/app/review/new?sample=sample_linkedin&tour=1" className="btn-teal">Run this example</Link>
                <Link href="/app/evaluation" className="btn-ghost">See accuracy numbers</Link>
              </div>
            </div>
            <div className="card space-y-4 p-6 text-sm">
              <p className="leading-relaxed">
                Say hello to <mark className="rounded bg-danger-100 px-0.5">India&apos;s #1</mark> and <mark className="rounded bg-danger-100 px-0.5">100% secure</mark> payments app!{" "}
                <mark className="rounded bg-info-100 px-0.5">Paywise</mark> now settles in <mark className="rounded bg-amber-100 px-0.5">under 5 seconds</mark> for every merchant. Download today and{" "}
                <mark className="rounded bg-amber-100 px-0.5">never worry again</mark>!
              </p>
              <div className="flex items-start gap-3 rounded-xl bg-paper-100 p-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
                <p>
                  <strong>CLM-04 · critical.</strong> “100% secure” is an absolute claim (brand_book.pdf p14). Closest approved fact F-112: “bank-grade AES-256 encryption”.
                </p>
              </div>
              <div className="flex items-start gap-3 rounded-xl bg-paper-100 p-3">
                <Scale className="mt-0.5 h-4 w-4 shrink-0 text-amber" aria-hidden="true" />
                <p>
                  <strong>CLM-03 · outdated.</strong> Matches F-086, superseded by F-087 on 2 Sep 2026. Suggest “under 10 seconds” (drift 0.09).
                </p>
              </div>
              <div className="flex items-start gap-3 rounded-xl bg-paper-100 p-3">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden="true" />
                <p>Brand Score 24 → 97 after one round of accepted suggestions. The approver signs off; the receipt shows a verified audit chain.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto mb-20 max-w-4xl px-6">
          <div className="card flex flex-col items-center gap-4 bg-navy p-10 text-center text-paper-50">
            <h2 className="text-3xl font-bold tracking-tight">See it on your own copy</h2>
            <p className="max-w-[52ch] text-paper-200">Paste anything about PayWise, or use one of four sample drafts. It takes about ten seconds.</p>
            <Link href="/app/review/new?tour=1" className="btn bg-teal px-6 py-3 text-base text-white hover:bg-teal-700">Try the live demo</Link>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
