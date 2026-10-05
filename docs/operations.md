# Operations and recovery

Run commands from `collector/`, or supply `--env-file /path/to/collector/.env`. Relative `DATA_DIR` is anchored to the configuration file’s folder. Default data is `.collector-data/outbox.sqlite`. One process lock protects the queue; do not run another worker on the same database.

| Command | Purpose |
| --- | --- |
| `vid2idea init` | Create a protected configuration template without overwriting |
| `vid2idea notion-sources` | List accessible Notion data source names and IDs |
| `vid2idea doctor --check-notion` | Check configuration, subscription login, media prerequisites and Notion schema/project access |
| `vid2idea import-history` | Queue accessible history, retaining progress across failures |
| `vid2idea run` | Listen for links, check history every five minutes, process jobs and poll refresh requests |
| `vid2idea once` | Process one pending job without connecting to Discord; run only when the service is stopped |
| `vid2idea status` | Read local heartbeat and queue safely while the service runs |

Prefix these with `uv run --locked --extra media` when using the repository environment. Importing history queues work; `run` or repeated `once` processes it. Check **Refresh article** in Notion to enqueue an intentional generation/research retry. Failed publication reuses saved output, rather than consuming another model call.

## Linux user service

Verify a foreground run first. The provided service assumes the checkout is `~/code/vid2idea`; adjust **WorkingDirectory**, **ExecStart** and **PATH** together if it lives elsewhere. Ensure PATH contains Codex, Node.js, FFmpeg and FFprobe. A path under `.collector-tools/bin` is an optional place for your own trusted binaries, not a shipped bundle.

From the repository root:

```bash
mkdir -p ~/.config/systemd/user
cp collector/service/vid2idea.service ~/.config/systemd/user/vid2idea.service
systemctl --user daemon-reload
systemctl --user enable --now vid2idea
journalctl --user -u vid2idea -n 50 --no-pager
```

The service uses private file permissions and restarts after failures. It requires an awake computer and an available user service manager. Choose any logout/startup behavior explicitly for your machine. To stop it, run `systemctl --user disable --now vid2idea`; retain the private database and configuration.

## WSL2 startup

[Systemd services do not keep WSL alive](https://learn.microsoft.com/en-us/windows/wsl/systemd). After installing the user service, the optional PowerShell installer creates one **Vid2Idea Collector** logon task that keeps an attached WSL process running with limited privileges and no stored password.

Run `collector/service/install-windows-startup.ps1` from Windows PowerShell, supplying your own `-Distribution`, `-LinuxUser` and `-RepositoryPath`. Paths must contain no spaces or shell syntax; the installer validates them and refuses to replace a differently configured existing task. Inspect it with `Get-ScheduledTask -TaskName 'Vid2Idea Collector'`. Deliberately verify a reboot/sign-in on your own machine before relying on unattended startup. Sleep and shutdown pause collection; history catch-up resumes afterward.

To remove that exact task, use `Unregister-ScheduledTask -TaskName 'Vid2Idea Collector'` in PowerShell, and disable the Linux user service. Do not delete unrelated tasks.

## Status and troubleshooting

`Ready` means processing completed without recorded gaps, not independent fact checking. `Partial` keeps a useful brief with coverage gaps or incomplete research. `Blocked` records an inaccessible/unsupported source. Safe JSON events contain job IDs and error codes rather than source bodies, URLs or tokens.

| Symptom | First check |
| --- | --- |
| Private configuration error | Run `chmod 600 collector/.env` from the repository root; use your own regular file, not a symlink |
| Missing configuration | Fill the required fields in `.env`; use the correct working directory |
| `notion_schema_mismatch` | Match every property type/option and the Projects relation in setup.md |
| `notion_project_mismatch` / `notion_project_unavailable` | Use an active project page in the configured Projects data source |
| Notion authentication/access/missing error | Connection token, granted database/project access, and correct data source IDs |
| Codex unavailable or subscription login required | `codex login status`, CLI 0.160.0 compatibility and subscription usage |
| No new entries | Local `status`, awake computer, bot channel permissions and Message Content Intent |
| Partial research | Read coverage notes; restore Codex/search availability and request Refresh article |
| Identity/ownership/create reconciliation error | Stop guessing; preserve SQLite and inspect the existing page and journal before recovery |

## Backups

Keep `.env`, SQLite, generated snapshots, images, and journals private. A database backup made while the service is active must use SQLite's consistent backup API, not copy the main file alone. From `collector/`, this standard-library example backs up the default database without resetting jobs:

```bash
umask 077
python3 - <<'PY'
import sqlite3
from pathlib import Path
source = Path('.collector-data/outbox.sqlite').resolve()
target = Path('.collector-data/backups/outbox.sqlite')
target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
if target.exists():
    raise SystemExit('Backup already exists; choose a new destination.')
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as live:
    with sqlite3.connect(target) as backup:
        live.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
PY
```

If `DATA_DIR` is customized, adjust both paths first. Copy the environment file separately into protected storage. For restoration, stop the service and preserve the current state before restoring a consistent database and its matching configuration. Preserve identities, page mappings and publication journals; starting with an empty database can create duplicate pages. No hosted application is required for normal recovery.
