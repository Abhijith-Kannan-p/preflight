// Full-page error states in the Proof Desk style: a proof slip marked "not found" or
// "returned", with one clear way forward.

import Link from "next/link";

export function ErrorSheet({
  code,
  stamp,
  title,
  text,
  action,
  reference,
}: {
  code: string;
  stamp: string;
  title: string;
  text: string;
  action?: React.ReactNode;
  reference?: string;
}) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4 py-12">
      <section className="proof-paper relative w-full max-w-lg px-8 py-8" aria-labelledby="error-title">
        <p className="label">Proof returned · {code}</p>
        <h1 id="error-title" className="mt-2 font-serif text-[28px] leading-tight text-ink">
          {title}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-graphite">{text}</p>
        <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-rule pt-4">
          {action ?? (
            <Link href="/app" className="btn-primary">
              Back to the desk
            </Link>
          )}
          <Link href="/" className="text-sm text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">
            Home
          </Link>
        </div>
        {reference && <p className="mt-4 font-mono text-[11px] text-graphite">Reference {reference}</p>}
        <div
          aria-hidden="true"
          className="absolute -right-2 top-6 rotate-[8deg] border-[3px] border-double border-signal px-3 py-1 font-mono text-[13px] font-medium uppercase tracking-[0.18em] text-signal mix-blend-multiply"
        >
          {stamp}
        </div>
      </section>
    </div>
  );
}
