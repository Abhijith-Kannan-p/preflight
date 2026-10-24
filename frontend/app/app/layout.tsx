"use client";

import { useEffect, useState } from "react";
import { SWRConfig } from "swr";

import { AppHeader } from "@/components/AppHeader";
import { EngineGate } from "@/components/EngineGate";
import { Footer } from "@/components/Footer";
import { HelpPanel } from "@/components/HelpPanel";
import { fetcher } from "@/lib/api";
import { SessionProvider } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [help, setHelp] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "?" && !["INPUT", "TEXTAREA"].includes(target.tagName)) setHelp(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <SWRConfig value={{ fetcher, revalidateOnFocus: false }}>
      <SessionProvider>
        <div className="flex min-h-screen flex-col">
          <AppHeader onHelp={() => setHelp(true)} />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
            <EngineGate>{children}</EngineGate>
          </main>
          <Footer />
        </div>
        <HelpPanel open={help} onClose={() => setHelp(false)} />
      </SessionProvider>
    </SWRConfig>
  );
}
