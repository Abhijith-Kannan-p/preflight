# Questions for Abhijith

Non-blocking. Work continues with the default shown; change it any time.

1. **Sandbox cookie across domains.** Done this way: the frontend proxies only
   `/api/sandbox/*` to Render through a Next.js rewrite, so the httpOnly sandbox cookie is
   first-party and works in incognito. Everything else still calls Render directly with the
   signed token (which already names the sandbox), so live progress streams are not proxied.
   No new environment variable (the rewrite reuses `NEXT_PUBLIC_API_URL`).
2. **Visual review speed target (< 6 s per image).** Measured after tuning (Phase 4): 6.8 s per
   banner on 0.1 CPU, 1.3 s on a normal CPU, both reported. Earlier estimate: Measured 5.4–6.5 s on Render's 0.1 CPU for a
   1200×630 banner, 0.5 s on one full CPU. Default: report both honestly; sample images are
   OCR'd once on the server at boot and cached (labelled "cached" in the UI).
3. **Gemini free-tier limits.** The Rulebook Compiler and Guideline Health rewording add LLM
   calls. Default: deterministic fallbacks everywhere, with a visible banner when the LLM is
   unavailable.
