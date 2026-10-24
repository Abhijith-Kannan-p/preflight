"use client";

// A perspective tunnel of real Preflight findings that fly towards the reader as the page
// scrolls. Driven by normal page scroll (sticky stage), so it never traps the wheel.

import { MotionValue, motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { LogoMark } from "./Logo";

interface Card {
  kind: "critical" | "major" | "minor" | "supported";
  rule: string;
  text: string;
  detail: string;
}

const CARDS: Card[] = [
  { kind: "critical", rule: "CLM-04", text: "100% secure", detail: "→ bank-grade encrypted" },
  { kind: "major", rule: "CLM-03 · F-087", text: "under 5 seconds", detail: "Outdated → under 10 seconds" },
  { kind: "supported", rule: "F-045", text: "zero MDR on UPI", detail: "Supported · quote verified" },
  { kind: "critical", rule: "DSC-02", text: "PayWise Pay Later", detail: "Needs “Subject to eligibility.”" },
  { kind: "minor", rule: "TRM-02", text: "Paywise", detail: "→ PayWise" },
  { kind: "critical", rule: "CLM-02 · F-046", text: "zero fees on cards", detail: "Contradicted → a 1.5% fee" },
  { kind: "supported", rule: "F-112", text: "AES-256 encryption", detail: "Supported · entailment 0.99" },
  { kind: "major", rule: "CLM-06", text: "never worry again", detail: "→ pay with confidence" },
  { kind: "major", rule: "TON-01", text: "Playful 0.80", detail: "Target 0.30 for PayWise" },
  { kind: "supported", rule: "F-032", text: "2 million merchants", detail: "Supported · numbers match" },
];

const KIND_STYLE: Record<Card["kind"], { ring: string; label: string; badge: string }> = {
  critical: { ring: "ring-danger/30", label: "Critical", badge: "bg-danger-50 text-danger-700" },
  major: { ring: "ring-amber/30", label: "Major", badge: "bg-amber-50 text-amber-700" },
  minor: { ring: "ring-info/30", label: "Minor", badge: "bg-info-50 text-info-700" },
  supported: { ring: "ring-teal/30", label: "Supported", badge: "bg-teal-50 text-teal-700" },
};

const LAYOUT = CARDS.map((card, i) => {
  const golden = i * 137.5 * (Math.PI / 180);
  return {
    card,
    index: i,
    cos: Math.cos(golden),
    sin: Math.sin(golden),
    rx: 0.3 + (i % 3) * 0.07,
    ry: 0.27 + (i % 2) * 0.08,
    rotate: (i % 2 === 0 ? 1 : -1) * (2 + (i % 4) * 1.5),
  };
});

interface Stage {
  width: number;
  height: number;
  mobile: boolean;
}

function usePointer(enabled: boolean) {
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const x = useSpring(rawX, { stiffness: 60, damping: 25, mass: 0.5 });
  const y = useSpring(rawY, { stiffness: 60, damping: 25, mass: 0.5 });
  useEffect(() => {
    if (!enabled) return;
    const move = (e: PointerEvent) => {
      rawX.set((e.clientX / window.innerWidth - 0.5) * 2);
      rawY.set((e.clientY / window.innerHeight - 0.5) * 2);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, [enabled, rawX, rawY]);
  return { x, y };
}

function FindingCard({ card }: { card: Card }) {
  const style = KIND_STYLE[card.kind];
  return (
    <div className={`h-full w-full rounded-2xl bg-paper-50/95 p-4 shadow-lift ring-1 ${style.ring} backdrop-blur`}>
      <div className="flex items-center justify-between gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${style.badge}`}>{style.label}</span>
        <span className="font-mono text-[10px] text-navy-500">{card.rule}</span>
      </div>
      <p className="mt-3 text-base font-semibold leading-snug text-navy">“{card.text}”</p>
      <p className="mt-1 text-xs text-navy-500">{card.detail}</p>
    </div>
  );
}

function TunnelCard({
  item,
  progress,
  pointer,
  stage,
}: {
  item: (typeof LAYOUT)[number];
  progress: MotionValue<number>;
  pointer: { x: MotionValue<number>; y: MotionValue<number> };
  stage: Stage;
}) {
  const span = 0.55;
  // Shifted back so the first few cards are already in flight before any scrolling.
  const start = (item.index / LAYOUT.length) * (1 - span) - 0.22;
  const local = useTransform(progress, [start, start + span], [0, 1]);
  const z = useTransform(local, [0, 1], [stage.mobile ? -1200 : -1700, stage.mobile ? 350 : 500]);
  const opacity = useTransform(local, [0, 0.18, 0.82, 0.98], [0, 1, 1, 0]);
  const width = stage.mobile ? Math.max(150, Math.min(190, stage.width * 0.42)) : Math.max(200, Math.min(260, stage.width * 0.17));
  const baseX = item.cos * stage.width * item.rx;
  const baseY = item.sin * stage.height * item.ry;
  const pan = stage.mobile ? 18 : 40;
  const transform = useTransform([z, pointer.x, pointer.y], ([cz, px, py]: number[]) => {
    return `translate3d(calc(-50% + ${baseX - px * pan}px), calc(-50% + ${baseY - py * pan}px), ${cz}px) rotateZ(${item.rotate}deg)`;
  });
  return (
    <motion.div style={{ width, transform, opacity }} className="absolute left-1/2 top-1/2 h-[118px] will-change-transform">
      <FindingCard card={item.card} />
    </motion.div>
  );
}

export function TunnelHero() {
  const ref = useRef<HTMLDivElement>(null);
  const prefersReduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  // Only honour the media query after hydration, so server and client HTML match.
  const reduce = mounted && Boolean(prefersReduced);
  const [stage, setStage] = useState<Stage>({ width: 1440, height: 900, mobile: false });

  useEffect(() => {
    const update = () => setStage({ width: window.innerWidth, height: window.innerHeight, mobile: window.innerWidth < 768 });
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const progress = useSpring(scrollYProgress, { stiffness: 80, damping: 30, restDelta: 0.0001 });
  const pointer = usePointer(!reduce);
  const titleScale = useTransform(progress, [0, 0.6, 1], [1, 1.08, 1.25]);
  const titleOpacity = useTransform(progress, [0, 0.75, 0.95], [1, 1, 0]);
  const hintOpacity = useTransform(progress, [0, 0.1], [1, 0]);

  return (
    <section ref={ref} className={reduce ? "relative" : "relative h-[230vh]"} aria-label="Preflight introduction">
      <div
        className="sticky top-0 flex h-[100svh] w-full items-center justify-center overflow-hidden"
        style={{ perspective: stage.mobile ? "900px" : "1200px", transformStyle: "preserve-3d" }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(#E4DCC6_1px,transparent_1px)] [background-size:28px_28px] [mask-image:radial-gradient(ellipse_70%_70%_at_50%_50%,#000_60%,transparent_100%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(15,139,126,0.10)_0%,transparent_65%)]" />
        <div className="pointer-events-none absolute h-[48vmin] w-[48vmin] rounded-full border border-teal/15" />
        <div className="pointer-events-none absolute h-[76vmin] w-[76vmin] rounded-full border border-dashed border-paper-200" />

        {mounted && !reduce && (
          <div className="pointer-events-none absolute inset-0" style={{ transformStyle: "preserve-3d" }} aria-hidden="true">
            {LAYOUT.map((item) => (
              <TunnelCard key={item.index} item={item} progress={progress} pointer={pointer} stage={stage} />
            ))}
          </div>
        )}

        <motion.div style={reduce ? undefined : { scale: titleScale, opacity: titleOpacity }} className="relative z-10 flex max-w-2xl flex-col items-center px-6 text-center">
          <span className="mb-5 inline-flex items-center gap-2 rounded-full border border-paper-200 bg-paper-50/80 px-3 py-1 text-xs font-medium text-navy-500 backdrop-blur">
            <LogoMark className="h-4 w-4" /> Pre-publication brand governance
          </span>
          <h1 className="text-6xl font-bold leading-[0.95] tracking-tighter text-navy sm:text-8xl">Preflight</h1>
          <p className="mt-5 text-xl font-medium text-navy-700 sm:text-2xl">Content cleared before it goes live.</p>
          <p className="mt-3 max-w-[48ch] text-sm text-navy-500 sm:text-base">
            Every draft is checked against your brand rules and approved facts. Every finding cites its source. People approve.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href="/app/review/new?tour=1" className="btn-teal px-6 py-3 text-base shadow-lift">
              Try the live demo
            </Link>
            <a href="#how-it-works" className="btn-ghost px-5 py-3">How it works</a>
          </div>
          <p className="mt-3 text-xs text-navy-500">No sign-up. You start as abhi1, a content creator at the fictional PayWise.</p>
        </motion.div>

        {!reduce && (
          <motion.div style={{ opacity: hintOpacity }} className="pointer-events-none absolute bottom-8 flex flex-col items-center gap-2 text-[11px] font-medium uppercase tracking-[0.3em] text-navy-500">
            <span>Scroll</span>
            <div className="h-6 w-px bg-gradient-to-b from-teal to-transparent" />
          </motion.div>
        )}
      </div>
    </section>
  );
}
