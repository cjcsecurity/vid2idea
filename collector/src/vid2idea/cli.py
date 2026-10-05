import argparse
import importlib.util
import json
import logging
import shutil
import sys
from pathlib import Path
from filelock import FileLock, Timeout
from .config import Settings


def doctor(settings,check_notion=False):
    missing = settings.missing()
    checks = {'missing_configuration':missing,'ai_configured':settings.ai_configured,'ai_provider':settings.ai_provider,'vision_configured':settings.ai_provider == 'codex' or bool(settings.ai_vision_model),
        'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),
        'scrapling':importlib.util.find_spec('scrapling') is not None,
        'yt_dlp':importlib.util.find_spec('yt_dlp') is not None,
        'faster_whisper':importlib.util.find_spec('faster_whisper') is not None}
    checks['publishing_backend']=settings.publishing_backend
    if check_notion:
        from .notion_api import NotionAPI,PublicationError
        try:
            api=NotionAPI(settings)
            try:
                api.validate_schema()
                api.request('GET',f'/pages/{settings.notion_vid2idea_project_page_id}')
                api.bot_id
                checks['notion_connection']='verified'
            finally:
                api.close()
        except (PublicationError,ValueError) as error:
            checks['notion_connection']=getattr(error,'code','notion_invalid_configuration')
            missing.append('NOTION_CONNECTION')
    print(json.dumps(checks,indent=2))
    return 0 if not missing and all(checks[k] for k in ('ai_configured','ffmpeg','ffprobe','scrapling','yt_dlp','faster_whisper')) else 1


def main():
    parser = argparse.ArgumentParser(description='Collect Discord links into your private idea library')
    parser.add_argument('command', choices=['doctor','import-history','run','once','status','migration-export','migration-import'])
    parser.add_argument('--check-notion',action='store_true')
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    # Third-party logs can contain URLs, bodies, and authentication responses.
    logging.getLogger().setLevel(logging.CRITICAL)
    try:
        settings = Settings.from_env()
    except ValueError:
        print('Invalid configuration. Check the names and formats in .env.example.',file=sys.stderr)
        return 1
    if args.command == 'doctor':
        return doctor(settings,args.check_notion)
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
