# Release preparation checks

Verified October 5, 2026 for version 0.1.0. This source bundle is prepared for review; no public repository, package index release or GitHub Actions run is claimed.

| Check | Result |
| --- | --- |
| Fresh Python 3.12 environment, `uv sync --extra media --locked` | Passed; shipped lockfile unchanged |
| Full regression suite from the repository root | 112 passed, two opt-in legacy live checks skipped; seven upstream deprecation warnings |
| `uv build --directory collector` | Wheel and source distribution built successfully |
| Built package inventory | Wheel: 33 files; source distribution: 57 files; private runtime files excluded |
| Fresh wheel installation in a separate environment | Console help and empty local status passed without configuration or service calls |
| Setup schema comparison | All 18 required property names/types match the publisher; required select options and Projects destination documented |
| Data source discovery example | Read-only Notion search returned HTTP 200 with expected data source object types |
| CI definition | YAML parsed, pinned action commits resolved, local test/build/CLI steps passed |
| Source/built-artifact secret scans | Official Gitleaks 8.30.1, download SHA-256 verified; no unsuppressed findings |
| Separate privacy/inventory checks | Operational credential/ID markers and private data directories absent from source inventory and extracted built members |
| Runtime comparison | All 28 runtime Python files byte-identical to the working collector |
| Test-only changes | Operational fixture identifiers replaced with synthetic values; three synthetic fixture lines explicitly annotated for Gitleaks |
| Independent review | No Critical/Important implementation findings; two factual documentation corrections applied and checked against primary evidence |
| Existing installation | Same live service process, no restart; private local status showed no pending or publication errors |

The secret scanner initially matched synthetic Discord IDs in tests. Only those three verified fixture lines use standard `gitleaks:allow` annotations. No global scanner exemption was introduced. Separate privacy comparisons covered the complete release inventory. Secret scanning and marker checks do not constitute a complete security audit.

## Limits

GitHub-hosted CI has not run because no repository was published during preparation. A clean source installation and a wheel CLI smoke test were performed; the complete bot/Notion onboarding flow was not repeated in a second new workspace. The existing integration has live verification, but new users must verify their own permissions, schema, platform access and model usage.

Linux/WSL2 and Codex CLI 0.160.0 are the tested baseline. macOS, other Codex versions and deliberate Windows reboot/sign-in behavior are not verified here. Native Windows is unsupported. Compatibility modules remain for the old storage format; no hosted website or cloud database is required by the documented workflow.
