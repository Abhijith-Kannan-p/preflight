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
   unavailable. (Compiler: one call per brand book, about 5 s; when it fails, structured
   extraction still produces rules and a banner says so.)
4. **Compiler evaluation on a brand book we wrote.** The spec's "three public brand books" are
   copyrighted and do not map to PayWise's rules. Default: one fictional 20-page PayWise Brand
   Book with hand labels, stated on the Evaluation page. Say if you want a second book.
5. **Held-out claim precision (0.67).** The 0.90 target is met on the tuning set (0.94) but
   not on claims written afterwards. Default: report both and stop tuning, so the held-out set
   stays honest. Further work would need a fresh held-out set.
