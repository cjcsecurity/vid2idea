import argparse
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from filelock import FileLock, Timeout
from .config import ConfigurationError, Settings
from .environment import runtime_environment


def doctor(settings,check_notion=False,check_ai=False):
    missing = settings.missing()
    checks = {'missing_configuration':missing,'ai_configured':settings.ai_configured,'ai_provider':settings.ai_provider,'vision_configured':settings.ai_provider != 'openai' or bool(settings.ai_vision_model),
        'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),
        'scrapling':importlib.util.find_spec('scrapling') is not None,
        'yt_dlp':importlib.util.find_spec('yt_dlp') is not None,
        'faster_whisper':importlib.util.find_spec('faster_whisper') is not None}
    checks['publishing_backend']=settings.publishing_backend
    checks['supported_platform'] = sys.platform.startswith('linux')
    checks['rapidocr'] = importlib.util.find_spec('rapidocr') is not None
    if settings.ai_provider == 'codex':
        try:
            login = subprocess.run([settings.codex_command, 'login', 'status'], capture_output=True, text=True, timeout=15, env=runtime_environment())
            checks['codex_login'] = 'verified' if login.returncode == 0 and 'logged in using chatgpt' in (login.stdout + login.stderr).lower() else 'codex_subscription_login_required'
        except (OSError, subprocess.TimeoutExpired):
            checks['codex_login'] = 'codex_unavailable'
        if checks['codex_login'] != 'verified':
            missing.append('CODEX_LOGIN')
    if settings.ai_provider in ('claude','gemini'):
        from .cli_agents import agent_status
        checks['agent_login']=agent_status(settings)
        if checks['agent_login'] not in ('verified','login_unverified'):
            missing.append('AGENT_LOGIN')
    if check_ai:
        from .ai import generate_brief
        from .models import Evidence
        try:
            generate_brief(Evidence(text='Example Tool is a fictional bookmarking tool.',source_url='https://example.com'),'',
                           settings.model_copy(update={'project_roots':'','github_owner':'','brief_context':''}))
            checks['ai_generation']='verified'
        except Exception as error:
            checks['ai_generation']=getattr(error,'code','model_unavailable')
            missing.append('AI_GENERATION')
    if check_notion:
        from .notion_api import NotionAPI,PublicationError
        try:
            api=NotionAPI(settings)
            try:
                api.validate_schema()
                api.validate_project(settings.notion_vid2idea_project_page_id)
                api.bot_id
                checks['notion_connection']='verified'
            finally:
                api.close()
        except (PublicationError,ValueError) as error:
            checks['notion_connection']=getattr(error,'code','notion_invalid_configuration')
            missing.append('NOTION_CONNECTION')
    checks['next_steps'] = []
    if checks.get('codex_login') not in (None, 'verified'):
        checks['next_steps'].append('Run codex login, choosing ChatGPT authentication.')
    if checks.get('agent_login') == 'login_unverified' and checks.get('ai_generation') != 'verified':
        checks['next_steps'].append('Run vid2idea auth for Google login, then doctor --check-ai to verify a real model call.')
    elif checks.get('agent_login') not in (None,'verified','login_unverified'):
        checks['next_steps'].append('Follow docs/providers.md for the supported CLI version and vid2idea auth.')
    if not checks['ai_configured'] and settings.ai_provider=='openai':
        checks['next_steps'].append('Set AI_BASE_URL and AI_MODEL; configure AI_API_KEY when your endpoint requires it.')
    if missing:
        checks['next_steps'].append('Complete the local configuration using docs/setup.md.')
    if not all(checks[k] for k in ('scrapling','yt_dlp','faster_whisper','rapidocr')):
        checks['next_steps'].append('Install media dependencies: uv sync --extra media --locked.')
    if not checks['ffmpeg'] or not checks['ffprobe']:
        checks['next_steps'].append('Install FFmpeg and put ffmpeg and ffprobe on PATH.')
    print(json.dumps(checks, indent=2))
    return 0 if not missing and all(checks[k] for k in ('ai_configured','ffmpeg','ffprobe','scrapling','yt_dlp','faster_whisper','rapidocr','supported_platform')) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description='Turn Discord links into researched Notion briefs.', formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='init            Create a private configuration template\nauth            Sign in to the selected CLI provider\nnotion-sources  List data source names and IDs shared with your connection\ndoctor          Check configuration, AI login and media tools\nimport-history  Queue links from Discord history\nrun             Watch Discord and process the queue\nonce            Process one queued job\nstatus          Read queue/publication status without changing jobs\nmigration-*     Import/export legacy backups\n\nStart here: vid2idea init, edit .env, then vid2idea doctor --check-notion.\nSetup: https://github.com/cjcsecurity/vid2idea/blob/main/docs/setup.md')
    parser.add_argument('command', choices=['init','auth','notion-sources','doctor','import-history','run','once','status','migration-export','migration-import'])
    parser.add_argument('--version', action='version', version='vid2idea 0.1.0')
    parser.add_argument('--env-file', type=Path, help='Explicit private configuration file; relative DATA_DIR is based on its folder (default: ./.env)')
    parser.add_argument('--check-notion',action='store_true', help='Verify Notion schema, project membership and connection access during doctor')
    parser.add_argument('--check-ai',action='store_true', help='Make one synthetic brief to verify the selected AI provider (uses quota)')
    parser.add_argument('--backup',type=Path, help='Legacy migration backup folder')
    parser.add_argument('--dry-run',action='store_true', help='Inspect a legacy import without writing')
    args = parser.parse_args(argv)
    # Third-party logs can contain URLs, bodies, and authentication responses.
    logging.getLogger().setLevel(logging.CRITICAL)
    try:
        if args.command == 'init':
            from .setup import initialize_config
            path = args.env_file if args.env_file is not None else Path('.env')
            initialize_config(path)
            print('Created private configuration. Edit it locally, choose your provider, then run vid2idea doctor --check-notion. Provider setup: docs/providers.md')
            return 0
        settings = Settings.from_env(args.env_file)
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except ValueError:
        print('Invalid configuration. Check the names and formats in .env.example.',file=sys.stderr)
        return 1
    if args.command == 'doctor':
        return doctor(settings,args.check_notion,args.check_ai)
    if args.command == 'auth':
        from .cli_agents import login_agent
        from .urls import SourceError
        try:
            return login_agent(settings)
        except SourceError as error:
            print(error.code,file=sys.stderr)
            return 1
    if args.command == 'notion-sources':
        from .setup import discover_sources
        from .notion_api import PublicationError
        try:
            print(json.dumps(discover_sources(settings), indent=2))
            return 0
        except ConfigurationError as error:
            print(str(error), file=sys.stderr)
        except (PublicationError, ValueError, KeyError, TypeError) as error:
            print(json.dumps({'error_code': getattr(error, 'code', 'notion_invalid_configuration')}), file=sys.stderr)
        return 1
    if not sys.platform.startswith('linux') and args.command not in ('status',):
        print('This release supports Linux and WSL2. Use WSL2 on Windows.', file=sys.stderr)
        return 1
    if args.command in ('status','migration-export','migration-import'):
        from .migration import export_backup,import_backup,local_status
        from .notion_api import PublicationError
        try:
            if args.command=='status':
                print(json.dumps(local_status(settings),indent=2)); return 0
            if args.command=='migration-export':
                if settings.model_copy(update={'publishing_backend':'supabase'}).missing(discord=False):
                    raise PublicationError('migration_cloud_configuration_missing')
                backup=export_backup(settings,root=args.backup)
                print(json.dumps({'backup':str(backup.resolve()),'inventory':str((backup/'inventory.json').resolve())})); return 0
            if not args.backup:
                print('--backup is required for migration-import.',file=sys.stderr); return 1
            if args.dry_run:
                from types import SimpleNamespace
                store=SimpleNamespace(api=SimpleNamespace(data_source_id=settings.notion_library_data_source_id))
                report=import_backup(args.backup,store,None,dry_run=True)
                print(json.dumps(report,indent=2)); return 0
            settings=settings.model_copy(update={'publishing_backend':'notion'})
        except Exception as error:
            print(json.dumps({'error_code':getattr(error,'code','migration_unavailable')}),file=sys.stderr); return 1
    missing = settings.missing(discord=args.command not in ('once','migration-import'))
    if missing:
        print('Missing configuration: ' + ', '.join(missing),file=sys.stderr)
        return 1
    from .notion_store import make_store
    from .discord_client import IdeaClient
    from .outbox import Outbox
    from .worker import Worker
    settings.data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock = FileLock(settings.data_dir / 'collector.lock',timeout=0)
    try:
        with lock:
            box = Outbox(settings.data_dir/'outbox.sqlite')
            try:
                cloud = make_store(settings,box)
                if args.command=='migration-import':
                    report=import_backup(args.backup,cloud,box)
                    print(json.dumps({'migrated':report['migrated'],'skipped':report['skipped'],
                        'model_calls':report['model_calls'],'pending_jobs':report['pending_local_jobs'],
                        'report':str((args.backup/'migration-report.json').resolve())}))
                    return 0 if not report['skipped'] else 1
                worker = Worker(box,cloud,settings,entry_point=args.command)
                if args.command == 'once':
                    try:
                        for request in cloud.list_retry_requests():
                            box.enqueue_retry(request)
                    except Exception:
                        from .worker import event
                        event('refresh_poll_unavailable','once',job_id='sync',error_code='cloud_unavailable')
                    result = worker.run_once()
                    cloud.record_status(box.pending_count(),worker.last_error_code)
                    print(result)
                    return 0 if result in ('idle','processed') else 1
                client = IdeaClient(settings,box,cloud,worker if args.command == 'run' else None,history_only=args.command == 'import-history')
                client.run(settings.discord_token.get_secret_value(),log_handler=None)
                if args.command == 'import-history' and client.history_error:
                    print('History import failed. Saved progress is retained; retry import-history.',file=sys.stderr)
                    return 1
            finally:
                if 'cloud' in locals() and hasattr(cloud,'api'):
                    cloud.api.close()
                box.close()
    except Timeout:
        print('Another collector instance holds the process lock.',file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Collector could not start. Run vid2idea doctor and check service access.',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
