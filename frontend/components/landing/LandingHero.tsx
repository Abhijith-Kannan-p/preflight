"use client";

// The landing page's first screen: the flock forms PREFLIGHT, with the headline and the two
// actions below it. The text and buttons are server-rendered; only the canvas waits for the
// browser. The preset follows the theme live (dusk on the Warm Night Desk, paper on Paper Desk).

import { ArrowDown, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { MurmurationWordmark } from "./MurmurationWordmark";

function useDocumentTheme(): "light" | "dark" {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const root = document.documentElement;
    const read = () => setTheme(root.dataset.theme === "dark" ? "dark" : "light");
    read();
    const watch = new MutationObserver(read);
    watch.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => watch.disconnect();
  }, []);
  return theme;
}

export function LandingHero({ children }: { children?: React.ReactNode }) {
  const slot = useRef<HTMLDivElement>(null);
  const theme = useDocumentTheme();

  const seeHow = (e: React.MouseEvent<HTMLAnchorElement>) => {
    const target = document.getElementById("overview");
    if (!target) return;
    e.preventDefault();
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
    target.focus({ preventScroll: true });
  };

  return (
    <section aria-labelledby="hero-title" className="hero relative isolate flex min-h-[100svh] flex-col overflow-hidden bg-paper">
      <MurmurationWordmark word="PREFLIGHT" preset={theme === "dark" ? "dusk" : "paper"} slotRef={slot} birdCount={3000} />
      {/* The header sits on top of the sky. */}
      <div className="relative z-20">{children}</div>
      <div ref={slot} className="relative mx-auto w-full max-w-6xl flex-1 basis-[30svh] px-4 sm:px-8" aria-hidden="true" />
      <div className="relative z-10 mx-auto flex w-full max-w-3xl flex-col items-center px-4 pb-[max(3.5rem,8svh)] pt-2 text-center">
        <div className="hero-scrim pointer-events-none absolute -inset-x-10 -inset-y-8 -z-10" aria-hidden="true" />
        <p className="kicker text-ink/80">Preflight · Pre-publication brand governance</p>
        <h1 id="hero-title" className="mt-3 font-serif text-[40px] font-medium leading-[1.05] tracking-tight text-ink sm:text-[56px] lg:text-[64px]">
          Every claim earns its place.
        </h1>
        <div className="mt-8 flex w-full flex-col items-stretch justify-center gap-3 sm:w-auto sm:flex-row sm:items-center">
          <Link href="/app/review/new?tour=1" className="btn bg-hero-action px-6 py-3 text-base text-hero-action-on hover:opacity-90">
            Open the demo desk <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <a href="#overview" onClick={seeHow} className="btn-ghost px-6 py-3 text-base">
            See how it works <ArrowDown className="h-4 w-4" aria-hidden="true" />
          </a>
        </div>
      </div>
    </section>
  );
}
