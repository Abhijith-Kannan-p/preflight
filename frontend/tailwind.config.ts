import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#1B2A4A", 50: "#F3F5F9", 100: "#E4E8F0", 700: "#2A3B5F" },
        teal: { DEFAULT: "#0F8B7E", 50: "#E8F5F3", 700: "#0B6B61" },
        amber: { DEFAULT: "#D98E1F", 50: "#FCF4E6", 700: "#9A6312" },
        danger: { DEFAULT: "#C8463D", 50: "#FBECEB", 700: "#9E352E" },
        info: { DEFAULT: "#2F6FB3", 50: "#EAF1F9", 700: "#245689" },
        purple: { DEFAULT: "#6B4FA0", 50: "#F1EDF7", 700: "#523C7B" },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
