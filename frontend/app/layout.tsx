import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Preflight", template: "%s · Preflight" },
  description: "Content cleared before it goes live. Pre-publication brand governance with cited, explainable findings.",
};

export const viewport: Viewport = { themeColor: "#FBF8EF" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} min-h-screen font-sans`}>{children}</body>
    </html>
  );
}
