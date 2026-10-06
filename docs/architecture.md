# Architecture

The collector is one local Python process with a durable SQLite outbox and one processing worker. Discord capture continues while a source is processed. Notion is the reading interface and publishing destination.

| Module | Responsibility |
| --- | --- |
| `discord_client.py`, `capture.py`, `urls.py` | Read authorized channel history/events, extract links, validate and canonicalize URLs |
| `outbox.py`, `worker.py` | Durable jobs, history cursor, retry/backoff, process lock and safe events |
| `articles.py`, `videos.py`, `transcribe.py`, `ocr.py` | Extract article text or public video audio, on-screen text and sampled frames |
| `media_assets.py` | Normalize bounded source images into metadata-free JPEGs |
| `ai.py`, `codex.py`, `cli_agents.py`, `resources.py` | Structured generation and evidence-grounded resource identities |
| `project_context.py` | Optional bounded project descriptions from local folders and GitHub |
| `research.py` | Bounded selected-provider live-search pass, opened citations and unresolved answers |
| `local_library.py` | Stable source identity, provenance, snapshots and publication journals |
| `notion_api.py`, `notion_content.py`, `notion_store.py` | Validate schema, render native blocks, upload images and reconcile publication |
| `safe_proxy.py`, `pipeline.py` | Bounded public-source network extraction in a disposable child process |

Normal publishing uses Notion. `cloud.py` and `migration.py` retain compatibility with the previous storage format; no hosted website or cloud database is part of the documented setup.

## Generation and research

Source analysis uses the ChatGPT-authenticated Codex CLI by default, with structured output and selected images. Its tools, user configuration and collector credentials are excluded. Research is a separate bounded pass with live web search; only citations from successful page-open events are retained. This establishes that a page was opened, not that every generated claim is correct.

Set `AI_PROVIDER=openai` to generate briefs through an explicitly configured OpenAI-compatible endpoint. This mode disables automatic follow-up research, even if Codex is logged in. Use `codex`, `claude` or `gemini` for generation plus research; see the [provider matrix](providers.md) for experimental status and pinned CLI contracts. Without a usable subscription login or remaining usage, the Codex workflow retains retryable jobs or a source brief with incomplete research. Pin the model through `CODEX_MODEL`; otherwise the CLI chooses its default.

## Publication ownership

One canonical URL has a stable local identity and can retain multiple Discord shares. The Notion page is reconciled by its External ID. Native image upload IDs, generated snapshots and write journals persist across retry, so a publication retry need not repeat model generation.

The collector replaces its own generated section only after the new version is available. Human notes, favorites, stages, review status, edited project relations and unrelated page blocks are preserved. Uncertain writes, duplicate identities, ownership changes or trashed destinations may require review instead of blind replay. Keep the database and page mappings for recovery.
