# Security and privacy

This collector runs under your local operating-system user and holds Discord and Notion credentials. Restrict bot/connection access to the intended channel and databases. Keep `.env` and `.collector-data` private, exclude them from commits, and use protected backups.

Source analysis sends extracted content, selected images, Discord context and opted-in project summaries to the configured AI provider. Follow-up research is restricted to public resource identifiers and eligible questions, excluding private project descriptions and Discord notes. Notion publication includes the article, original shared URLs, sharing timestamps, channel/message identifiers and accompanying notes. Review your intended destinations and source permissions.

Local project discovery reads bounded descriptions, not full source trees or environment files. Do not point it at folders whose README content you cannot send to your chosen provider. The collector does not import browser cookies or bypass private-source access controls.

Public-source extraction uses URL validation, a bounded safety proxy, download/time limits and disposable processing processes. These controls reduce exposure; this early release is not a security boundary for hostile multi-user ingestion. Prefer a personal channel and treat links and generated output as untrusted data.

Before publishing changes, use a maintained secret scanner such as [Gitleaks](https://github.com/gitleaks/gitleaks), and inspect archive contents separately for private data and IDs. Secret detection does not prove that a bundle contains no personal content.

Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/cjcsecurity/vid2idea/security/advisories/new). Private reporting is enabled on this repository. Include affected versions, impact and a synthetic reproduction; never include real credentials or personal records. Do not disclose exploit details in a public issue. No response SLA is promised.

The alpha release receives best-effort fixes. Keep Python, FFmpeg and dependencies updated; use the reviewed AI CLI versions in docs/providers.md and review their compatibility before upgrading. CI runs regression tests, Gitleaks, Semgrep Community Edition and a known-advisory dependency audit. The pinned Scrapling Git dependency is not covered by pip-audit; static and secret scans cannot establish the absence of vulnerabilities.

Configuration is read only from the current folder or an explicit `--env-file`. It must be a regular file owned by you with private permissions. Values are not interpolated into other environment variables. Media/model children inherit an explicit runtime allowlist; they do not inherit arbitrary API or cloud credentials. Media demuxers are limited to self-contained MP4/MOV/WebM, and public-source connections are checked and pinned to public IP addresses. Codex generation runs without shell, connected apps or local tool access; research receives a restricted public payload. The worker still runs under your OS user and is not an OS container sandbox.

Claude Code runs in safe mode with explicit tool allowlists and no session persistence. Gemini uses a private collector-specific login profile; its CLI may retain local session files there. Keep the entire DATA_DIR private, including provider authentication and session state. Research in these adapters uses the public-address safety proxy. Their authenticated end-to-end behavior is experimental; see docs/providers.md for verification limits.
