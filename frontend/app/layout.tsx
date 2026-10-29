import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";

import { THEME_SCRIPT } from "@/lib/theme-script";

import "./globals.css";

// Self-hosted at build time by next/font: no runtime requests to Google.
const newsreader = Newsreader({ variable: "--font-newsreader", subsets: ["latin"], style: ["normal", "italic"] });
const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: { default: "Preflight", template: "%s · Preflight" },
  description: "Content cleared before it goes live. Pre-publication brand governance with cited, explainable findings.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F7F4EC" },
    { media: "(prefers-color-scheme: dark)", color: "#1C1816" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // The theme attribute is set before hydration by THEME_SCRIPT, so React must not warn.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${newsreader.variable} ${plexSans.variable} ${plexMono.variable} min-h-screen font-sans`}>{children}</body>
    </html>
  );
}
