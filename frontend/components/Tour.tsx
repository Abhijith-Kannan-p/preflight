"use client";

// A short, dismissible guided tour that points at real elements (data-tour="...").
// Re-open it from the "?" help panel at any time.

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

import { TOUR_EVENT } from "./HelpPanel";

export interface TourStep {
  target: string;
  title: string;
  text: string;
}

const DONE_KEY = "preflight.tour.done";
const autoStarted = new Set<string>();

function seen(): boolean {
  try {
    return window.localStorage.getItem(DONE_KEY) === "1";
  } catch {
    return false;
  }
}

function markSeen(): void {
  try {
    window.localStorage.setItem(DONE_KEY, "1");
  } catch {
    // Tour simply shows again next time.
  }
}

export function Tour({ steps, autoStart, ready }: { steps: TourStep[]; autoStart: boolean; ready: boolean }) {
  const [index, setIndex] = useState<number | null>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    // Auto-start at most once per page (not again after a re-check or a role switch).
    const key = window.location.pathname;
    if (ready && !autoStarted.has(key) && (autoStart || !seen())) {
      autoStarted.add(key);
      setIndex(0);
    }
  }, [ready, autoStart]);

  useEffect(() => {
    const open = () => setIndex(0);
    window.addEventListener(TOUR_EVENT, open);
    return () => window.removeEventListener(TOUR_EVENT, open);
  }, []);

  const measure = useCallback(() => {
    if (index === null) return;
    const el = document.querySelector(`[data-tour="${steps[index]?.target}"]`);
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      setRect(el.getBoundingClientRect());
    } else setRect(null);
  }, [index, steps]);

  useLayoutEffect(() => {
    measure();
    const timer = window.setTimeout(measure, 350);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
    };
  }, [measure]);

  const close = () => {
    markSeen();
    setIndex(null);
  };

  if (index === null) return null;
  const step = steps[index];
  const below = rect ? rect.bottom + 220 < window.innerHeight : true;
  const top = rect ? (below ? rect.bottom + 12 : Math.max(12, rect.top - 200)) : window.innerHeight / 2 - 100;
  const left = rect ? Math.min(Math.max(12, rect.left), window.innerWidth - 352) : window.innerWidth / 2 - 170;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label={`Guided tour, step ${index + 1} of ${steps.length}`}>
        {rect && (
          <div
            className="pointer-events-none fixed rounded-2xl ring-4 ring-teal transition-all duration-300"
            style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12, boxShadow: "0 0 0 9999px rgba(27,42,74,0.35)" }}
          />
        )}
        <motion.div
          key={index}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="fixed w-[340px] rounded-2xl border border-paper-200 bg-paper-50 p-4 shadow-lift"
          style={{ top, left }}
        >
          <p className="text-[11px] font-semibold uppercase tracking-wider text-teal-700">
            Step {index + 1} of {steps.length}
          </p>
          <h2 className="mt-1 font-semibold">{step.title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-navy-500">{step.text}</p>
          <div className="mt-4 flex items-center justify-between">
            <button type="button" onClick={close} className="text-xs font-medium text-navy-500 hover:underline">
              Skip tour
            </button>
            <div className="flex gap-2">
              {index > 0 && (
                <button type="button" className="btn-ghost py-1 text-xs" onClick={() => setIndex(index - 1)}>
                  Back
                </button>
              )}
              <button type="button" className="btn-teal py-1 text-xs" autoFocus onClick={() => (index + 1 < steps.length ? setIndex(index + 1) : close())}>
                {index + 1 < steps.length ? "Next" : "Got it"}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
