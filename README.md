# 2025

A curated public subset of my OpenClaw workspace.

This repository is prepared for GitHub publishing and intentionally includes only low-risk, reusable assets such as selected skills and documentation.

## Included

- `docs/` — project notes, command reference, design docs
- `skills/obsidian/` — Obsidian-related automation helpers
- `skills/github/` — GitHub skill metadata/docs
- `skills/notion/` — Notion skill metadata/docs
- `skills/summarize/` — summarize skill metadata/docs
- `skills/weather/` — weather skill metadata/docs
- `skills/find-skills/` — skill discovery metadata/docs
- `skills/skillhub-preference/` — skill preference metadata/docs

## Intentionally Excluded

This repo does **not** aim to publish the entire workspace. The following categories are intentionally excluded from GitHub:

- local secrets (`.env`, keys, credentials)
- runtime state (`logs/`, `*.pid`, local caches)
- generated outputs and artifacts
- large models / SDK binaries
- local data snapshots / DuckDB / Parquet
- personal notes / memory / Obsidian vault content

## Notes

- Some skills in the private workspace depend on local data, credentials, or proprietary SDKs and are therefore not part of this public subset.
- The Obsidian daily summary generator in `skills/obsidian/daily_summary.py` writes Markdown files directly to a local vault path inside the workspace and is primarily intended for local automation.

## Publishing approach

This repository will be pushed using a whitelist approach rather than publishing the full workspace wholesale.
