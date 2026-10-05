# v0.1.0 release verification

Checks performed on 2026-10-05. This is an alpha; the evidence below describes specific checks rather than a general security guarantee.

## Local checks

- Locked `uv` installation on Linux/WSL2, Python 3.12.14.
- 127 tests passed; two legacy live Supabase tests skipped. Seven upstream deprecation warnings remain.
- Regression coverage for private env-file loading, environment precedence, no interpolation, no process environment mutation, non-overwriting setup, safe errors, Notion source discovery and project membership, and arbitrary-credential exclusion from processing children.
- Real FFmpeg/FFprobe fixtures verify that an HLS playlist cannot read another local media file and that MP4 remains readable.
- Gitleaks 8.30.1, Semgrep Community Edition 1.179.0, and pip-audit 2.10.0 are the selected security checks. Semgrep's initial scan ran 200 applicable rules over 31 source/automation files with no findings.
- The initial dependency audit returned zero known advisories among 88 checked distributions. Scrapling's pinned Git revision is skipped by pip-audit and must be reviewed separately. The lock also contains platform-specific packages not installed in this environment.
- Source and wheel builds completed. Release checks also require a fresh wheel configuration/CLI smoke test and scans of the final source and built distributions.

## Publication gate

The candidate is undergoing independent review before public code publication. Repository publication, hosted CI and release asset verification will be recorded here after they complete. CI has minimum read permissions, immutable action pins, isolated secret scanning, static analysis, locked dependency auditing and weekly checks. Dependabot is configured for uv and GitHub Actions.

## Practical limits

Offline fixtures do not prove every public source can be downloaded. A full first-time onboarding in a separate new Notion workspace has not been performed. Native Windows/macOS and a deliberate Windows reboot/sign-in are unverified. Public platform access, Notion plan limits and Codex subscription limits apply. The separately running personal installation was not changed by this release work.

The public repository and artifacts are built from a dedicated sanitized checkout, not the operational collector's history or data directory. Source images and sample content use synthetic examples; credentials, saved articles and workspace/channel identifiers are excluded. Keep local state and backups private.
