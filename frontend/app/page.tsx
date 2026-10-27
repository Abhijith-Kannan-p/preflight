import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Footer } from "@/components/Footer";
import { LandingProof } from "@/components/LandingProof";
import { Logo } from "@/components/Logo";
import { Splash } from "@/components/Splash";
import { API_URL, GITHUB_URL } from "@/lib/api";

const PROOF_POINTS = [
  { mark: "01", title: "Cited, or it is not raised", text: "Every finding names a brand-book rule and page, or an approved fact with its version. A validator drops anything ungrounded." },
  { mark: "02", title: "Claims checked locally", text: "Factual claims go through retrieval, a local NLI model, exact number comparison and a quote check. The hosted LLM proposes; it never decides truth." },
  { mark: "03", title: "Cleared by a person", text: "Critical findings block approval. The approver's sign-off and every decision are written into a hash-chained audit log." },
];

const STEPS = [
  { n: "01", title: "Paste or upload", text: "Text, Markdown, DOCX or PDF, for LinkedIn, X, email or a press release." },
  { n: "02", title: "Preflight checks", text: "Terminology, disclaimers, channel limits, readability, tone and the Claim Ledger run in parallel." },
  { n: "03", title: "Work the margin notes", text: "Accept, edit, dispute or escalate each note. Re-check and watch the Brand Score climb." },
  { n: "04", title: "Clear for publication", text: "The approver stamps it and a Clearance Certificate records who, when, and what changed." },
];

export default function Landing() {
  return (
    <>
      <Splash />
      <header className="border-b border-rule bg-paper">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <nav className="flex items-center gap-5 text-sm">
            <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="hidden text-graphite hover:text-ink sm:inline">API</a>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hidden text-graphite hover:text-ink sm:inline">GitHub</a>
            <Link href="/app" className="btn-ghost py-1.5">Sign in to the desk</Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-7xl px-4 pb-16 pt-12 sm:px-6 lg:pt-16" aria-labelledby="hero">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-end">
            <div>
              <p className="label">Pre-publication brand governance · PayWise demo</p>
              <h1 id="hero" className="mt-3 max-w-[18ch] font-serif text-[40px] leading-[1.1] text-ink sm:text-[48px]">
                Every claim checked against the rulebook before it goes live.
              </h1>
            </div>
            <div>
              <p className="max-w-[56ch] text-base leading-relaxed text-graphite">
                Preflight reads a draft the way a careful editor reads a proof. It marks what breaks the brand book, checks each factual claim against approved facts, proposes the smallest fix, and holds the draft until a person clears it.
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Link href="/app/review/new?tour=1" className="btn-primary px-5 py-2.5">
                  Open the demo desk <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <Link href="/app/review/new?sample=sample_linkedin&tour=1" className="text-sm text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">
                  Run the specimen below
                </Link>
              </div>
            </div>
          </div>

          <div className="mt-12">
            <LandingProof />
          </div>
        </section>

        <section className="border-y border-rule bg-sheet" aria-labelledby="proof-points">
          <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
            <h2 id="proof-points" className="label">Why a reviewer can trust the marks</h2>
            <ol className="mt-6 grid gap-x-10 gap-y-8 md:grid-cols-3">
              {PROOF_POINTS.map((p) => (
                <li key={p.mark} className="border-t border-ink pt-4">
                  <span className="font-mono text-xs text-graphite">{p.mark}</span>
                  <h3 className="mt-1 font-serif text-xl text-ink">{p.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-graphite">{p.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="how-it-works" className="mx-auto max-w-7xl scroll-mt-20 px-4 py-16 sm:px-6" aria-labelledby="how">
          <h2 id="how" className="font-serif text-[28px] text-ink">How it works</h2>
          <ol className="mt-8 grid border-t border-rule md:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n} className="border-b border-rule py-5 md:border-b-0 md:border-r md:px-5 md:first:pl-0 md:last:border-r-0">
                <span className="font-mono text-xs text-teal-700">{s.n}</span>
                <h3 className="mt-2 font-medium text-ink">{s.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-graphite">{s.text}</p>
              </li>
            ))}
          </ol>
          <div className="mt-10 flex flex-wrap items-center gap-4 border-t border-rule pt-6 text-sm">
            <Link href="/app/review/new?tour=1" className="btn-primary">Open the demo desk</Link>
            <Link href="/app/evaluation" className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">See the measured accuracy</Link>
            <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">Read the API</a>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
