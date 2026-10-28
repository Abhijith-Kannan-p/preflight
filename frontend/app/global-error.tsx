"use client";

// Last resort when the root layout itself fails: plain markup, no app styles assumed.
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#F7F4EC", color: "#1B2A4A", fontFamily: "Georgia, serif" }}>
        <main style={{ maxWidth: 520, margin: "15vh auto", padding: "32px", background: "#FFFDF8", border: "1px solid #E3DED2" }}>
          <p style={{ fontFamily: "monospace", fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "#5B6573" }}>Proof returned · 500</p>
          <h1 style={{ fontWeight: 400, fontSize: 28 }}>Preflight could not load</h1>
          <p style={{ fontFamily: "sans-serif", fontSize: 14, color: "#5B6573" }}>Something went wrong before the page could start. Please try again.</p>
          <button type="button" onClick={reset} style={{ marginTop: 16, padding: "8px 14px", background: "#1B2A4A", color: "#FFFDF8", border: 0, borderRadius: 4, cursor: "pointer" }}>
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
