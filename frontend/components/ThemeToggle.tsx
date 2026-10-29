"use client";

import { clsx } from "clsx";
import { Moon, Sun } from "lucide-react";

import { useTheme } from "@/lib/theme";

export function ThemeToggle({ withLabel = false }: { withLabel?: boolean }) {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "Paper Desk (light)" : "Warm Night Desk (dark)";
  return (
    <button type="button" onClick={toggle} aria-label={`Switch to ${next}`} title={`Switch to ${next}`} className={clsx("inline-flex items-center gap-2 rounded p-2 text-graphite transition-colors duration-150 hover:bg-raised hover:text-ink", withLabel && "w-full px-3 text-sm")}>
      {theme === "dark" ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
      {withLabel && <span>Switch to {next}</span>}
    </button>
  );
}
