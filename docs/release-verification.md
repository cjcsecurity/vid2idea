# v0.1.0 release verification

Checks performed on 2026-10-05. This is an alpha; the evidence below describes specific checks rather than a general security guarantee.

## Local checks

- Locked `uv` installation on Linux/WSL2, Python 3.12.14.
- 127 tests passed; two legacy live Supabase tests skipped. Seven upstream deprecation warnings remain.
- Regression coverage for private env-file loading, environment precedence, no interpolation, no process environment mutation, non-overwriting setup, safe errors, Notion source discovery and project membership, and arbitrary-credential exclusion from processing children.
- Real FFmpeg/FFprobe fixtures verify that an HLS playlist cannot read another local media file and that MP4 remains readable.
- Gitleaks 8.30.1, Semgrep Community Edition 1.179.0, and pip-audit 2.10.0 are the selected security checks. Semgrep's final local scan ran 200 applicable rules over 36 source/automation files with no findings; hosted static analysis also passed.
- The initial dependency audit returned zero known advisories among 88 checked distributions. Scrapling's pinned Git revision is skipped by pip-audit and must be reviewed separately. The lock also contains platform-specific packages not installed in this environment.
- Source and wheel builds completed. Fresh wheel installation, packaged configuration, private/non-overwriting init, help/version, empty status, missing-prerequisite doctor and explicit configuration from another folder passed. Twine 7.0.0 validated both package metadata sets. Source/distribution membership and private-data canaries passed; Gitleaks scanned committed history and the clean source archive. A fresh public clone installed from the lock and passed all 127 tests with two legacy live skips.

## Publication gate

The [public repository](https://github.com/cjcsecurity/vid2idea) is published with an MIT license. Independent review found no Critical or Important issues and independently verified real MP4/WebM audio and frame extraction plus the packaged setup flow. Its sole nonblocking suggestion, a fresh-wheel CI setup check, was implemented and passed.

Hosted [collector/build/secret checks](https://github.com/cjcsecurity/vid2idea/actions/runs/37385994827) and [dependency/static checks](https://github.com/cjcsecurity/vid2idea/actions/runs/37385994886) passed for commit `bb7ea0a`. Initial hosted testing exposed a hidden installed-Codex dependency in mocked fixtures; opt-in fake executable availability now makes those tests portable. CI installs FFmpeg so the real media safety checks execute rather than skip.

CI has minimum read permissions, immutable action pins, full-history and clean-source secret scanning, static analysis, locked dependency auditing and weekly checks. Dependabot is configured for uv and GitHub Actions. GitHub private vulnerability reporting, secret scanning, push protection and Dependabot security updates are enabled. The [alpha release](https://github.com/cjcsecurity/vid2idea/releases/tag/v0.1.0) carries full-source and Python distribution archives with SHA-256 checksums; asset verification is recorded in its release notes.

## Practical limits

Offline fixtures do not prove every public source can be downloaded. A full first-time onboarding in a separate new Notion workspace has not been performed. Native Windows/macOS and a deliberate Windows reboot/sign-in are unverified. Public platform access, Notion plan limits and Codex subscription limits apply. The separately running personal installation was not changed by this release work.

The public repository and artifacts are built from a dedicated sanitized checkout, not the operational collector's history or data directory. Source images and sample content use synthetic examples; credentials, saved articles and workspace/channel identifiers are excluded. Keep local state and backups private.
