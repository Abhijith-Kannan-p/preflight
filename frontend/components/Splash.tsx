"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import { LogoMark } from "./Logo";

const SPLASH_MS = 2000;

/** Full-screen "Preflight" intro shown for two seconds when the site opens. */
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
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-paper"
          exit={{ opacity: 0, transition: { duration: 0.5, ease: "easeInOut" } }}
          onClick={() => setVisible(false)}
        >
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(#E4DCC6_1px,transparent_1px)] [background-size:26px_26px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_50%,transparent_100%)]" />
          <motion.div
            initial={{ x: -120, y: 40, rotate: -18, opacity: 0 }}
            animate={{ x: 0, y: 0, rotate: 0, opacity: 1 }}
            transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          >
            <LogoMark className="h-16 w-16 drop-shadow-lg" />
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 12, letterSpacing: "0.3em" }}
            animate={{ opacity: 1, y: 0, letterSpacing: "-0.02em" }}
            transition={{ delay: 0.25, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
            className="mt-6 text-6xl font-bold text-navy sm:text-7xl"
          >
            Preflight
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            className="mt-3 text-sm font-medium uppercase tracking-[0.35em] text-teal-700"
          >
            Content cleared before it goes live
          </motion.p>
          <motion.div
            className="mt-10 h-0.5 w-40 origin-left rounded bg-teal"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: SPLASH_MS / 1000 - 0.2, ease: "linear" }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
