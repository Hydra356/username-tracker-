# username-tracker-
Inspiré de Sherlock, avec plus de sites.

Cyber — single-file username scanner with a neon/cyberpunk terminal UI.

• Async + fast: httpx + asyncio with concurrency control
• ~120 popular platforms (dev, social, art, music, gaming, etc.)
• One Python file, no external configs
• Futuristic neon UI (Rich): banner, panels, progress, live stats
• Exports results to JSON and Markdown (now with **robust, permission-safe output paths**)
• Interactive loop: scan again / tweak options / quit (no auto-close)
• Pretty tracebacks enabled when available; **graceful** without `pygments`
• **Self-tests**: run with `--self-test` to validate heuristics & path logic

Usage (Windows/macOS/Linux):
    pip install -U httpx[http2] rich pygments
    python cybersherlock.py --username <name>

Tip (Windows double‑click): if your working directory is `C:\\Windows\\System32`,
output will automatically fallback to your user folder.
