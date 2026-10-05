# vid2idea collector

Local Discord capture, multimedia evidence extraction, structured briefs,
cited follow-up research, and durable Notion publishing.

This package is configured from a local `.env` in its working directory.
It requires Python 3.12 and a Linux/WSL environment. The full application
also needs FFmpeg/FFprobe and a configured AI provider; default Codex
operation was verified with CLI 0.160.0. Install the `media` extra for
article extraction, video downloads, transcription, OCR and source images.

The source distribution includes tests and service examples. The repository
root contains the full installation guide, exact Notion schema, operations
guide, architecture notes, an illustrative brief and contribution guidance.
Use that guide for a complete installation rather than installing the wheel
alone and expecting it to provision Discord or Notion.

The default publishing integration is Notion. Legacy Supabase migration
compatibility remains in this release, but is not needed for normal operation.
