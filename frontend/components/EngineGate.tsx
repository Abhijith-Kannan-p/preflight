"use client";

// Free hosting sleeps when idle. Until /health answers with the models loaded, show a calm
// "Waking up the engine..." screen instead of errors, polling every two seconds.

import { motion } from "framer-motion";
import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Health } from "@/lib/types";

import { LogoMark } from "./Logo";
import { ErrorState } from "./ui";

export function EngineGate({ children }: { children: React.ReactNode }) {
  const { data, error } = useSWR<Health>("/health", fetcher, {
    refreshInterval: (latest) => (latest?.models_ready && latest.database ? 30_000 : 2_000),
    shouldRetryOnError: true,
    errorRetryInterval: 2_000,
  });
  const session = useSession();
  const ready = data?.database && data.models_ready;

  if (!ready) {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center" role="status" aria-live="polite">
        <motion.div animate={{ y: [0, -8, 0], rotate: [0, -4, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}>
          <LogoMark className="h-14 w-14" />
        </motion.div>
        <h1 className="mt-6 text-xl font-semibold">Waking up the engine…</h1>
        <p className="mt-2 max-w-[46ch] text-sm text-navy-500">
          {error || !data
            ? "The free server sleeps when nobody is using it. It usually starts in under a minute."
            : !data.database
              ? "Connecting to the database…"
              : "Loading the local verification models (embeddings and NLI). This happens once after a restart."}
        </p>
        <div className="mt-6 h-1 w-48 overflow-hidden rounded-full bg-paper-100">
          <motion.div className="h-full w-1/3 rounded-full bg-teal" animate={{ x: ["-100%", "300%"] }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }} />
        </div>
      </div>
    );
  }
  if (session.error) {
    return (
      <div className="mx-auto max-w-xl px-6 py-16">
        <ErrorState message={session.error} onRetry={() => window.location.reload()} />
      </div>
    );
  }
  if (!session.ready || !session.user) {
    return <div className="min-h-[60vh]" aria-busy="true" />;
  }
  return <>{children}</>;
}
