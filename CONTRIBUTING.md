# Contributing

Start with the README and architecture guide. Keep changes focused on turning saved links into useful, evidence-aware Notion briefs. Discuss large scope changes in an issue before building a new platform or destination.

Use Python 3.12 and the locked environment:

```bash
uv sync --directory collector --extra media --locked
uv run --directory collector --extra media --locked pytest tests -q
uv build --directory collector
```

Tests must use synthetic content, temporary SQLite databases and mocked external services. Keep real Discord IDs, Notion IDs, private repository descriptions, credentials and saved articles out of fixtures. Do not run the opt-in legacy live tests against a personal project. For behavior changes, test the observable outcome and failure/retry path; document any changed setup requirements.

Preserve human-owned Notion properties and blocks. Do not weaken public-source URL checks, process limits, credential isolation or publication reconciliation to make a test pass. A publication retry should reuse generated output wherever possible.

Describe the concrete before/after behavior and the checks you ran in the pull request. Changes to Notion schema must update setup documentation and compatibility tests together. Include no raw private logs or tokens in issues and PRs. Contributions to this project's code are provided under its MIT license; do not import third-party code without checking its license and attribution requirements.
