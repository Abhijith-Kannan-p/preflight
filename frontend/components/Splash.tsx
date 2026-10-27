"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

const SPLASH_MS = 2000;
const CHECKS = ["Terminology", "Disclaimers", "Claims", "Tone"];

/** Two-second opening: a proof slip runs its checks and takes the clearance stamp. */
export function Splash() {
  const [visible, setVisible] = useState(true);
  const reduce = useReducedMotion();

  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(false), reduce ? 600 : SPLASH_MS);
    return () => window.clearTimeout(timer);
  }, [reduce]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="splash"
          role="status"
          aria-label="Loading Preflight"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-paper px-4"
          exit={{ opacity: 0, transition: { duration: 0.35, ease: "easeInOut" } }}
          onClick={() => setVisible(false)}
        >
          <div className="sheet relative w-full max-w-sm px-8 py-7">
            <p className="label">Proof 01 · PayWise</p>
            <h1 className="mt-1 font-serif text-[40px] leading-none text-ink">Preflight</h1>
            <ol className="mt-5 divide-y divide-rule border-y border-rule font-mono text-xs">
              {CHECKS.map((c, i) => (
                <li key={c} className="flex items-center justify-between py-1.5 text-graphite">
                  {c}
                  <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: reduce ? 0 : 0.2 + i * 0.22, duration: 0.15 }} className="text-cleared">
                    ✓ done
                  </motion.span>
                </li>
              ))}
            </ol>
            <motion.div
              initial={{ opacity: 0, scale: 1.6, rotate: -14 }}
              animate={{ opacity: 1, scale: 1, rotate: -8 }}
              transition={{ delay: reduce ? 0 : 1.2, duration: 0.24, ease: [0.2, 0.9, 0.3, 1.2] }}
              className="absolute -bottom-4 right-4 border-[3px] border-double border-cleared bg-sheet/60 px-3 py-1 font-mono text-[13px] font-medium uppercase tracking-[0.18em] text-cleared"
            >
              Cleared
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
