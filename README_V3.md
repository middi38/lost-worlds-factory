# Lost Worlds Premium V3 — Automatic Factory

This package keeps the proven V2 renderer and adds a safe automatic production layer.

## What V3 adds
- Daily GitHub Actions production with no Run workflow tap required.
- Manual `auto` mode or manual selection of any slug in `topics/`.
- Curated topic rotation: no AI hallucinated history and no external LLM/API bill.
- Stable daily selection: re-running the same day does not unexpectedly switch topic.
- 12 curated starter episodes, each with its own narration, visual prompts, metadata and seed.
- Existing Kokoro -> Edge TTS fallback remains in `factory.py`.
- Existing Pollinations authenticated -> anonymous retry remains in `factory.py`.
- Build manifest (`selection.json`, `build.txt`) included with every artifact.
- Concurrency protection prevents two daily renders colliding.
- Pip + Kokoro caching reduces repeat setup time.
- Artifact retention is 30 days.

## Install on top of V2
Upload these paths into the repository, preserving folders:
- `auto_select.py`
- `.github/workflows/auto-factory.yml`
- `topics/*.json`

Do NOT delete the working `factory.py` or your existing `factory.yml` yet. V3 is additive, so V2 remains a fallback.

## Automatic schedule
Default is 15:17 UTC every day (18:17 in Turkey while UTC+3). GitHub scheduled workflows can start a little later than the exact cron minute.

## First test
Actions -> Lost Worlds Auto Factory V3 -> Run workflow -> leave `auto` -> Run workflow.
If it succeeds, download the `lost-worlds-v3-...` artifact and review the MP4 before adding automatic YouTube publishing.

## Safety/quality gate
V3 deliberately does NOT auto-publish to YouTube yet. Rendering and publishing are separated so a bad image, pronunciation, historical mistake, or provider outage cannot automatically go public. After several V3 outputs are reviewed, YouTube Data API publishing can be added with OAuth secrets and a visibility policy.

## Topic rotation
The included selector rotates through the curated catalog by UTC date. It will not repeat until the catalog cycles. Add more JSON files to `topics/` to extend the cycle indefinitely.
