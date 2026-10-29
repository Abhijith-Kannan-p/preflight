"use client";

// Night Desk (dark) and Paper Desk (light). The choice follows the system until the visitor
// picks one in the header; the pick is kept in localStorage (when storage is available).

import { useCallback, useEffect, useState } from "react";

import { THEME_KEY as KEY, THEME_QUERY as QUERY } from "./theme-script";

export type Theme = "light" | "dark";

function stored(): Theme | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const current = (document.documentElement.dataset.theme as Theme | undefined) ?? (media.matches ? "dark" : "light");
    setTheme(current);
    // Follow the system until the visitor has chosen.
    const onChange = () => {
      if (stored()) return;
      const next: Theme = media.matches ? "dark" : "light";
      apply(next);
      setTheme(next);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      apply(next);
      try {
        window.localStorage.setItem(KEY, next);
      } catch {
        // Private mode or blocked storage: the theme still changes for this page view.
      }
      return next;
    });
  }, []);

  return { theme, toggle };
}
