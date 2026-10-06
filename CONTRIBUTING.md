# Contributing

Start with the README, [shared agent instructions](AGENTS.md), and architecture guide. Codex, Claude Code and Gemini CLI can use the same commands; no client-specific plugin is required. Keep changes focused on turning saved links into useful, evidence-aware Notion briefs. Discuss large scope changes in an issue before building a new platform or destination.

Use Python 3.12 and the locked environment:

```bash
uv sync --directory collector --extra media --locked
uv run --directory collector --extra media --locked pytest tests -q
uv build --directory collector
```

Tests must use synthetic content, temporary SQLite databases and mocked external services. Keep real Discord IDs, Notion IDs, private repository descriptions, credentials and saved articles out of fixtures. Do not run the opt-in legacy live tests against a personal project. For behavior changes, test the observable outcome and failure/retry path; document any changed setup requirements.

Preserve human-owned Notion properties and blocks. Do not weaken public-source URL checks, process limits, credential isolation or publication reconciliation to make a test pass. A publication retry should reuse generated output wherever possible.

Describe the concrete before/after behavior and the checks you ran in the pull request. Changes to Notion schema must update setup documentation and compatibility tests together. Include no raw private logs or tokens in issues and PRs. Contributions to this project's code are provided under its MIT license; do not import third-party code without checking its license and attribution requirements.

CI checks source and automation with Semgrep, scans credentials with Gitleaks, and audits the locked dependency set with pip-audit. For a local dependency check:

```bash
uv export --directory collector --extra media --locked --no-dev --no-emit-project --no-hashes --output-file /tmp/vid2idea-requirements.txt --quiet
uvx --from pip-audit==2.10.0 pip-audit --no-deps --disable-pip -r /tmp/vid2idea-requirements.txt
```

The pinned Scrapling Git dependency is outside pip-audit's coverage. Review dependency changes and their upstream notes; keep the Scrapling revision and PyAV/Whisper compatibility constraint deliberate. Do not automatically merge dependency PRs.
