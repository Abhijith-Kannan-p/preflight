import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm, slightly yellowish paper background.
        paper: { DEFAULT: "#FBF8EF", 50: "#FFFDF7", 100: "#F6F1E3", 200: "#ECE4CF" },
        navy: { DEFAULT: "#1B2A4A", 50: "#F3F5F9", 100: "#E4E8F0", 300: "#9AA6BE", 500: "#4A5A7C", 700: "#2A3B5F" },
        teal: { DEFAULT: "#0F8B7E", 50: "#E8F5F3", 100: "#CDEBE6", 700: "#0B6B61" },
        amber: { DEFAULT: "#D98E1F", 50: "#FCF4E6", 100: "#F8E4BF", 700: "#9A6312" },
        danger: { DEFAULT: "#C8463D", 50: "#FBECEB", 100: "#F5D2CF", 700: "#9E352E" },
        info: { DEFAULT: "#2F6FB3", 50: "#EAF1F9", 100: "#D3E2F3", 700: "#245689" },
        purple: { DEFAULT: "#6B4FA0", 50: "#F1EDF7", 100: "#E1D8EF", 700: "#523C7B" },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(27,42,74,0.06), 0 4px 16px rgba(27,42,74,0.06)",
        lift: "0 10px 40px rgba(27,42,74,0.14)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out",
        shimmer: "shimmer 1.4s infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
