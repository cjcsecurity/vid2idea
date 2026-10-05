# Security and privacy

This collector runs under your local operating-system user and holds Discord and Notion credentials. Restrict bot/connection access to the intended channel and databases. Keep `.env` and `.collector-data` private, exclude them from commits, and use protected backups.

Source analysis sends extracted content, selected images, Discord context and opted-in project summaries to the configured AI provider. Follow-up research is restricted to public resource identifiers and eligible questions, excluding private project descriptions and Discord notes. Notion publication includes the article, original shared URLs, sharing timestamps, channel/message identifiers and accompanying notes. Review your intended destinations and source permissions.

Local project discovery reads bounded descriptions, not full source trees or environment files. Do not point it at folders whose README content you cannot send to your chosen provider. The collector does not import browser cookies or bypass private-source access controls.

Public-source extraction uses URL validation, a bounded safety proxy, download/time limits and disposable processing processes. These controls reduce exposure; this early release is not a security boundary for hostile multi-user ingestion. Prefer a personal channel and treat links and generated output as untrusted data.

Before publishing changes, use a maintained secret scanner such as [Gitleaks](https://github.com/gitleaks/gitleaks), and inspect archive contents separately for private data and IDs. Secret detection does not prove that a bundle contains no personal content.

When a public GitHub repository is created, use its **Security → Report a vulnerability** feature if private reporting is enabled. Until a private reporting channel exists, do not put exploit details, credentials or private data in a public issue. A public issue can ask the maintainer to establish a private contact route without including the vulnerability itself. No security response SLA is promised.
