# vid2idea collector

Local Discord capture, multimedia evidence extraction, structured briefs,
cited follow-up research, and durable Notion publishing.

Run `vid2idea init` to create a protected `.env` in your working directory.
Use `--env-file` to select an explicit file; relative data paths follow its folder.
It requires Python 3.12 and a Linux/WSL environment. The full application
also needs FFmpeg/FFprobe and a configured AI provider; default Codex
operation was verified with CLI 0.160.0. Experimental Claude Code and Gemini CLI adapters are documented in docs/providers.md, with pinned versions and their verification limits. Install the `media` extra for
article extraction, video downloads, transcription, OCR and source images.

The source distribution includes tests and service examples. The repository
root contains the full installation guide, exact Notion schema, operations
guide, architecture notes, an illustrative brief and contribution guidance.
Use that guide for a complete installation rather than installing the wheel
alone and expecting it to provision Discord or Notion.

The default publishing integration is Notion. Legacy Supabase migration
compatibility remains in this release, but is not needed for normal operation.

Full guide: https://github.com/cjcsecurity/vid2idea#readme
