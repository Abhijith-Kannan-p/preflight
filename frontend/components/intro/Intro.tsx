"use client";

// The intro before the landing page: a perspective tunnel of real review pieces that fly from
// far to near as you scroll, around the line "Every claim, cleared."
//
// It never traps the page: progress is the page's own scroll through a tall section with a
// sticky stage (wheel, trackpad, touch, arrow / PageDown / Space all work natively). Stopping
// in the last stretch glides on to the landing page; scrolling back up replays it in reverse;
// "Skip intro" jumps straight there. Reduced motion gets a still composition instead. Once a
// visitor has passed it, the rest of the session starts at the landing page (see the
// pre-paint script), with a "Replay intro" link.

import { motion, type MotionValue, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { ArrowDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { INTRO_KEY } from "@/lib/theme-script";

import { INTRO_CARDS } from "./IntroCards";

const TRAVEL_VH = 175; // extra scroll the tunnel takes: 1.75 viewport heights
const GOLDEN = 137.508;

/** Remember for the session; the pre-paint script hides the intro on the next page load
 * (not now: scrolling back up still replays it). */
export function markIntroSeen() {
  try {
    window.sessionStorage.setItem(INTRO_KEY, "seen");
  } catch {
    // Storage unavailable: the intro simply shows again next time.
  }
}

export function goToLanding(smooth = true) {
  markIntroSeen();
  document.getElementById("landing")?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
}

function useCompact() {
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return compact;
}

function TunnelCard({ progress, index, count, compact, children }: { progress: MotionValue<number>; index: number; count: number; compact: boolean; children: React.ReactNode }) {
  // Golden-angle spread around the centre, wider for later cards.
  const angle = (index * GOLDEN * Math.PI) / 180;
  const radius = 0.3 + 0.18 * Math.sqrt((index + 0.5) / count);
  const left = Math.cos(angle) * radius * (compact ? 60 : 92);
  // On a phone there is little room beside the title, so cards fly above and below it.
  const top = compact ? Math.sign(Math.sin(angle) || 1) * (24 + Math.abs(Math.sin(angle)) * 14) : Math.sin(angle) * radius * 74;
  const start = (index / count) * 0.55;
  const z = useTransform(progress, [start, start + 0.45], [-1700, 500]);
  const opacity = useTransform(progress, [start, start + 0.07, start + 0.34, start + 0.45], [0, 1, 1, 0]);
  return (
    // The stage fills the viewport, so percentages of it are viewport units; rounded so the
    // server and the browser write the same value.
    <motion.div className="absolute will-change-transform" style={{ left: `${(50 + left).toFixed(2)}%`, top: `${(50 + top).toFixed(2)}%`, x: "-50%", y: "-50%", z, opacity }}>
      <div style={{ transform: compact ? "scale(0.72)" : undefined }}>{children}</div>
    </motion.div>
  );
}

function Title({ scale, opacity }: { scale?: MotionValue<number>; opacity?: MotionValue<number> }) {
  return (
    <motion.div className="relative z-20 mx-auto max-w-3xl px-6 text-center [text-shadow:0_1px_24px_rgb(var(--paper))]" style={{ scale, opacity }}>
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-graphite">Preflight · pre-publication brand governance</p>
      <h2 className="mt-4 font-serif text-[44px] leading-[1.02] tracking-tight text-ink sm:text-[64px] lg:text-[80px]">Every claim, cleared.</h2>
      <p className="mt-4 text-base text-graphite sm:text-lg">Scroll to watch a draft get proofed.</p>
    </motion.div>
  );
}

function Backdrop() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      <div className="absolute inset-0 opacity-70 [background-image:radial-gradient(rgb(var(--graphite)/0.22)_1px,transparent_1px)] [background-size:28px_28px] [mask-image:radial-gradient(ellipse_at_center,black_35%,transparent_75%)]" />
      <svg className="absolute left-1/2 top-1/2 h-[140vmin] w-[140vmin] -translate-x-1/2 -translate-y-1/2" viewBox="0 0 100 100">
        {[14, 24, 34, 44].map((r) => (
          <circle key={r} cx="50" cy="50" r={r} fill="none" stroke="rgb(var(--rule))" strokeWidth="0.15" />
        ))}
      </svg>
    </div>
  );
}

function SkipButton({ label = "Skip intro", className }: { label?: string; className?: string }) {
  return (
    <button type="button" onClick={() => goToLanding()} className={className ?? "btn-ghost rounded-full py-1.5 text-sm"}>
      {label} <ArrowDown className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}

/** Reduced motion: no tunnel, a still composition around the title. */
function StillIntro() {
  const cards = INTRO_CARDS.filter((c) => ["draft", "note", "score-97", "stamp"].includes(c.id));
  const spots = ["left-[6%] top-[12%]", "right-[6%] top-[16%]", "left-[10%] bottom-[12%]", "right-[8%] bottom-[14%]"];
  return (
    <section className="intro-stage relative flex min-h-screen items-center justify-center overflow-hidden bg-paper" aria-label="Introduction">
      <Backdrop />
      <div className="absolute inset-0 hidden md:block" aria-hidden="true">
        {cards.map((c, i) => (
          <div key={c.id} className={`absolute ${spots[i]}`}>
            {c.node}
          </div>
        ))}
      </div>
      <div className="relative z-10 flex flex-col items-center gap-8">
        <Title />
        <SkipButton label="Continue" className="btn-primary px-5 py-2.5" />
      </div>
    </section>
  );
}

export function Intro() {
  const reduce = useReducedMotion();
  const compact = useCompact();
  const section = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: section, offset: ["start start", "end end"] });

  // Pointer parallax, spring-smoothed.
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const rotateY = useSpring(useTransform(px, [-1, 1], [-5, 5]), { stiffness: 60, damping: 18 });
  const rotateX = useSpring(useTransform(py, [-1, 1], [4, -4]), { stiffness: 60, damping: 18 });
  const titleScale = useTransform(scrollYProgress, [0, 0.9], [1, 1.4]);
  const titleOpacity = useTransform(scrollYProgress, [0, 0.72, 0.94], [1, 1, 0]);
  const promptOpacity = useTransform(scrollYProgress, [0, 0.08], [1, 0]);

  // A session that already passed the intro starts at the top of the landing page; the
  // browser would otherwise restore a scroll position measured with the intro above it.
  useEffect(() => {
    if (document.documentElement.dataset.intro !== "seen") return;
    window.history.scrollRestoration = "manual";
    window.scrollTo(0, 0);
  }, []);

  // Stopping in the last stretch on the way down glides on to the landing page.
  useEffect(() => {
    let last = scrollYProgress.get();
    let goingDown = true;
    let timer = 0;
    const off = scrollYProgress.on("change", (p) => {
      // Only the visitor's own scrolling counts: progress is also reported once on load.
      if (window.scrollY <= 0) return;
      goingDown = p >= last;
      last = p;
      if (p >= 0.99) markIntroSeen();
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (goingDown && p > 0.8 && p < 0.995) goToLanding();
      }, 160);
    });
    return () => {
      off();
      window.clearTimeout(timer);
    };
  }, [scrollYProgress]);

  if (reduce) return <StillIntro />;
  const cards = compact ? INTRO_CARDS.filter((c) => c.phone) : INTRO_CARDS;

  return (
    <section
      ref={section}
      className="intro-stage relative bg-paper"
      style={{ height: `calc(100vh + ${TRAVEL_VH}vh)` }}
      aria-label="Introduction"
      onPointerMove={(e) => {
        if (e.pointerType !== "mouse") return;
        px.set((e.clientX / window.innerWidth) * 2 - 1);
        py.set((e.clientY / window.innerHeight) * 2 - 1);
      }}
    >
      <div className="sticky top-0 flex h-screen items-center justify-center overflow-hidden">
        <Backdrop />
        <motion.div className="absolute inset-0 z-0" style={{ perspective: compact ? 700 : 1000, rotateX, rotateY, transformStyle: "preserve-3d" }} aria-hidden="true">
          {cards.map((c, i) => (
            <TunnelCard key={c.id} progress={scrollYProgress} index={i} count={cards.length} compact={compact}>
              {c.node}
            </TunnelCard>
          ))}
        </motion.div>
        <Title scale={titleScale} opacity={titleOpacity} />
        <div className="absolute right-4 top-4 z-30 sm:right-6 sm:top-6">
          <SkipButton />
        </div>
        <motion.div className="absolute bottom-8 left-1/2 z-30 flex -translate-x-1/2 flex-col items-center gap-2 text-sm text-graphite" style={{ opacity: promptOpacity }}>
          <span>Scroll to explore</span>
          <SkipButton label="Skip intro" className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs text-ink underline decoration-rule underline-offset-4 hover:decoration-ink" />
        </motion.div>
      </div>
    </section>
  );
}

/** Shown on the landing page once the intro has been passed this session. */
export function ReplayIntro() {
  return (
    <button
      type="button"
      className="replay-intro text-sm text-graphite underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink"
      onClick={() => {
        delete document.documentElement.dataset.intro;
        try {
          window.sessionStorage.removeItem(INTRO_KEY);
        } catch {
          // ignore
        }
        window.scrollTo({ top: 0, behavior: "auto" });
      }}
    >
      Replay intro
    </button>
  );
}
