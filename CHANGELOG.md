# Changelog

## Unreleased

- Experimental Claude Code and Gemini CLI generation/research adapters, with pinned contracts and isolated model tools. Authenticated end-to-end validation is still needed for both.
- Provider login and synthetic generation checks; setup failures retain queued work.
- Shared Codex/Claude/Gemini contributor instructions and clearer provider/onboarding documentation.
- Polished README preview and full product demo.

## 0.1.0 — 2026-10-05 (alpha)

First public release: a local Discord collector that publishes illustrated, researched resource briefs to a private Notion Library.

- Article extraction; public video captions/transcription, OCR and sampled vision.
- Resource names and grounded links, practical use cases, optional project context and cited research.
- Durable queue, history catch-up, publication reconciliation and preservation of personal Notion fields.
- Protected configuration initialization, explicit env-file loading, source ID discovery and actionable readiness checks.
- Public-IP network guard, media container restrictions, subprocess credential isolation, bounded processing and safe error codes.
- Locked dependencies, pinned GitHub Actions, tests, builds, secret/static/dependency checks and weekly update PRs.

Tested on Linux/WSL2 and Python 3.12 with Codex CLI 0.160.0. Native Windows/macOS, a separate new Notion workspace onboarding, and deliberate Windows reboot/sign-in remain unverified. Public-source platform availability and subscription/Notion limits apply. Legacy Supabase migration compatibility is retained; no cloud website is required.
