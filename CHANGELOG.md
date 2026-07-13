# Changelog

## 3.0.0 — 2026-07-13
- Expanded from 25 → **68 tools** covering full installed Kaggle CLI surface
- Kernels: search filters, files, init, topics, fixed push `-p`, delete `-y`
- Datasets: files, metadata, status, init, topics, fixed list flags (no invalid `--page-size`)
- Competitions: files, submissions, team-submissions, episodes, replay, logs, pages, topics
- Models: full create/update/delete + instances + versions tree
- Forums, benchmarks, quota, config
- Live-tested read paths against real Kaggle API (account `mtrakretech`)
- Soft-fail notes: some Kaggle endpoints 400/404/429 depending on account/rate limits

## 2.1.0 — 2026-07-13
- Public packaging: pyproject, LICENSE, multi-client examples
- Docs for Claude Desktop, Claude Code, Codex CLI, Cursor, Hermes, Windsurf, OpenCode, VS Code, Continue
- Safer HTTP log handler
- KAGGLE_API_TOKEN env passthrough for kaggle CLI v2.2.3+
- Windows launcher (`kaggle-mcp.cmd`)
- `main()` entry point for `pip install` console script

## 2.0.0 — 2026-07-07
- 25 tools (kernels, datasets, competitions, models, account)
- stdio + HTTP SSE transports
- No hardcoded credentials
