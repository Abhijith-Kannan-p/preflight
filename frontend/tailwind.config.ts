import type { Config } from "tailwindcss";

// "Proof Desk" design tokens. Colours live as CSS variables in app/globals.css; this file maps
// them to Tailwind names. Colour carries meaning only: large areas stay paper and ink.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  // `dark:` variants follow the Warm Night Desk theme attribute, not the media query.
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    // 0 for the proof sheet and certificate, 6 to 10 for controls and cards, pills for badges.
    borderRadius: {
      none: "0",
      sm: "4px",
      DEFAULT: "6px",
      md: "6px",
      lg: "10px",
      xl: "10px",
      "2xl": "10px",
      "3xl": "10px",
      full: "999px",
    },
    extend: {
      colors: {
        paper: { DEFAULT: v("paper"), 50: v("sheet"), 100: v("paper-deep"), 200: v("rule") },
        sheet: v("sheet"),
        raised: v("raised"),
        action: { DEFAULT: v("action"), hover: v("action-hover") },
        "on-action": v("on-action"),
        "on-signal": v("on-signal"),
        "hero-action": { DEFAULT: v("hero-action"), on: v("on-hero-action") },
        oxblood: v("oxblood"),
        ink: { DEFAULT: v("ink"), soft: v("ink-soft") },
        graphite: v("graphite"),
        rule: v("rule"),
        // Semantic colours.
        teal: { DEFAULT: v("teal"), 50: v("teal-wash"), 100: v("teal-wash-strong"), 700: v("teal-deep") },
        signal: { DEFAULT: v("signal"), 50: v("signal-wash"), 700: v("signal-deep") },
        amber: { DEFAULT: v("amber"), 50: v("amber-wash"), 100: v("amber-wash-strong"), 700: v("amber-deep") },
        slate: { DEFAULT: v("slate"), 50: v("slate-wash"), 100: v("slate-wash-strong"), 700: v("slate-deep") },
        cleared: { DEFAULT: v("cleared"), 50: v("cleared-wash"), 700: v("cleared-deep") },
        // Legacy names kept for unconverted screens; they resolve to Proof Desk colours.
        navy: { DEFAULT: v("ink"), 50: v("paper"), 100: v("rule"), 300: v("graphite-light"), 500: v("graphite"), 700: v("ink-soft") },
        danger: { DEFAULT: v("signal"), 50: v("signal-wash"), 100: v("signal-wash-strong"), 700: v("signal-deep") },
        info: { DEFAULT: v("slate"), 50: v("slate-wash"), 100: v("slate-wash-strong"), 700: v("slate-deep") },
        purple: { DEFAULT: v("graphite"), 50: v("paper-deep"), 100: v("rule"), 700: v("ink-soft") },
      },
      fontFamily: {
        sans: ["var(--font-plex-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-newsreader)", "Georgia", "serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        // 12 / 14 / 16 / 20 / 28 / 40 scale.
        xs: ["12px", "16px"],
        sm: ["15px", "22px"],
        base: ["16px", "24px"],
        lg: ["20px", "28px"],
        xl: ["20px", "28px"],
        "2xl": ["28px", "34px"],
        "3xl": ["28px", "34px"],
        "4xl": ["40px", "44px"],
        "5xl": ["40px", "44px"],
        "6xl": ["56px", "58px"],
        "7xl": ["72px", "72px"],
        "8xl": ["88px", "86px"],
      },
      boxShadow: {
        card: "none",
        lift: "0 1px 0 rgb(var(--rule)), 0 12px 32px -16px rgb(var(--shadow) / 0.35)",
        sheet: "0 1px 1px rgb(var(--shadow) / 0.08), 0 18px 40px -24px rgb(var(--shadow) / 0.45)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-in": { from: { transform: "translateX(100%)" }, to: { transform: "translateX(0)" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        tick: {
          "0%": { opacity: "0", transform: "scale(0.4)" },
          "70%": { opacity: "1", transform: "scale(1.15)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        stamp: {
          "0%": { opacity: "0", transform: "scale(1.6) rotate(-14deg)" },
          "60%": { opacity: "1", transform: "scale(0.96) rotate(-8deg)" },
          "100%": { opacity: "1", transform: "scale(1) rotate(-8deg)" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
        "slide-in": "slide-in 200ms ease-out",
        shimmer: "shimmer 1.4s infinite",
        stamp: "stamp 240ms ease-out both",
        tick: "tick 200ms ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
