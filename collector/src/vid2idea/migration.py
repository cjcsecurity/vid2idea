"""Owner-scoped protected exports and resumable imports; deliberately no AI imports."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .cloud import CloudStore, PUBLICATION_FIELDS
from .models import SourceCapture, RetryRequest
from .notion_api import PublicationError


def private_write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name(path.name+'.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'wb') as file:
        file.write(value.encode() if isinstance(value,str) else value)
        file.flush(); os.fsync(file.fileno())
    temp.chmod(0o600); os.replace(temp,path)


def backup_sqlite(source,target):
    if not Path(source).exists():
        return
    src=sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
    dst=sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()


def owner_rows(client,table,owner):
    rows=[]; offset=0
    while True:
        chunk=client.table(table).select('*').eq('owner_id',owner).order('owner_id' if table=='collector_status' else 'id').range(offset,offset+499).execute().data
        rows.extend(chunk)
        if len(chunk)<500:
            return rows
        offset+=500


def export_backup(settings,*,root=None):
    owner=str(UUID(settings.owner_id))
    root=Path(root or settings.data_dir/'notion-migration')
    root.mkdir(parents=True,exist_ok=True,mode=0o700); root.chmod(0o700)
    directory=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(uuid4())[:8])
    directory.mkdir(mode=0o700)
    cloud=CloudStore(settings)
    data={'format':1,'owner_id':owner,'exported_at':datetime.now(timezone.utc).isoformat(),
          'ideas':owner_rows(cloud.client,'ideas',owner),
          'source_shares':owner_rows(cloud.client,'source_shares',owner),
          'collector_status':owner_rows(cloud.client,'collector_status',owner),'images':[]}
    # Complete original records are backed up before downloading their private files.
    private_write(directory/'cloud.json',json.dumps(data,ensure_ascii=False,indent=2))
    for idea in data['ideas']:
        prefix=f"{owner}/{UUID(idea['id'])}/"
        for image in idea.get('images') or []:
            path=image['path']
            if not path.startswith(prefix) or '/' in path[len(prefix):] or not path.endswith('.jpg'):
                raise PublicationError('migration_image_scope')
            content=cloud.client.storage.from_('idea-images').download(path)
            sha=hashlib.sha256(content).hexdigest()
            if len(content)>204800 or not content.startswith(b'\xff\xd8\xff') or path[len(prefix):]!=sha+'.jpg':
                raise PublicationError('migration_invalid_image')
            filename='images/'+sha+'.jpg'
            private_write(directory/filename,content)
            data['images'].append({'idea_id':idea['id'],'source_path':path,'file':filename,'sha256':sha,
                                   'caption':image.get('caption','Source image'),'timestamp_seconds':image.get('timestamp_seconds')})
    private_write(directory/'cloud.json',json.dumps(data,ensure_ascii=False,indent=2))
    backup_sqlite(settings.data_dir/'outbox.sqlite',directory/'outbox.sqlite')
    if Path('.env').exists():
        private_write(directory/'collector.env',Path('.env').read_bytes())
    private_write(directory/'inventory.json',json.dumps(inventory(directory),indent=2))
    return directory


def read_backup(directory):
    data=json.loads((Path(directory)/'cloud.json').read_text())
    if data.get('format')!=1:
        raise PublicationError('migration_backup_format')
    owner=data['owner_id']
    ids={idea['id'] for idea in data['ideas']}
    if any(row.get('owner_id')!=owner for row in data['ideas']+data['source_shares']+data.get('collector_status',[])):
        raise PublicationError('migration_owner_scope')
    if any(row['idea_id'] not in ids for row in data['source_shares']+data.get('images',[])):
        raise PublicationError('migration_identity_scope')
    return data


def inventory(directory):
    data=read_backup(directory); ideas=data['ideas']; states={}
    for row in ideas:
        states[row['processing_status']]=states.get(row['processing_status'],0)+1
    local={'states':{},'cached_results':0,'cursors':{}}
    db_path=Path(directory)/'outbox.sqlite'
    if db_path.exists():
        db=sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            local['states']=dict(db.execute('select state,count(*) from jobs group by state').fetchall())
            local['cached_results']=db.execute('select count(*) from jobs where cached_result is not null').fetchone()[0]
            local['cursors']=dict(db.execute('select channel_id,message_id from cursors').fetchall())
        finally:
            db.close()
    return {'ideas':len(ideas),'source_shares':len(data['source_shares']),'images':len(data.get('images',[])),
            'briefs':sum(bool(x.get('brief')) for x in ideas),'processing_statuses':states,
            'notes_characters':sum(len(x.get('personal_notes','')) for x in ideas),
            'favorites':sum(bool(x.get('favorite')) for x in ideas),
            'stages':{name:sum(x.get('stage')==name for x in ideas) for name in ('saved','trying','done')},
            'pending_cloud_requests':sum(bool(x.get('retry_request_id')) for x in ideas),'local_jobs':local}


def stored_payload(directory,data,idea):
    payload={k:idea[k] for k in PUBLICATION_FIELDS if k in idea and k!='images'}
    payload['image_uploads']=[]
    for original in idea.get('images') or []:
        matches=[x for x in data.get('images',[]) if x['idea_id']==idea['id'] and x['source_path']==original['path']]
        if len(matches)!=1:
            raise PublicationError('migration_image_missing')
        image=matches[0]
        relative=Path(image['file'])
        if relative.parts!=('images',image['sha256']+'.jpg'):
            raise PublicationError('migration_image_scope')
        content=(Path(directory)/relative).read_bytes()
        if hashlib.sha256(content).hexdigest()!=image['sha256']:
            raise PublicationError('migration_invalid_image')
        payload['image_uploads'].append({'sha256':image['sha256'],'data':base64.b64encode(content).decode(),
                                       'caption':image['caption'],'timestamp_seconds':image.get('timestamp_seconds')})
    return payload


def import_backup(directory,store,outbox,*,dry_run=False):
    directory=Path(directory); data=read_backup(directory)
    report={'format':1,'dry_run':dry_run,'inventory':inventory(directory),'migrated':0,'skipped':0,
            'model_calls':0,'entries':[],'pending_requests_imported':0,'destination':store.api.data_source_id,
            'verification':{},'rollback_backup':str(directory.resolve())}
    if dry_run:
        # Validate stored image coverage as well as counting rows, without opening a page.
        for idea in data['ideas']:
            stored_payload(directory,data,idea)
        return report
    for idea in data['ideas']:
        id=idea['id']; entry={'idea_id':id,'external_id':'vid2idea:idea:'+id}
        try:
            shares=[SourceCapture(**{key:row[key] for key in ('channel_id','message_id','original_url','note','shared_at')},
                                  canonical_url=idea['canonical_url']) for row in data['source_shares'] if row['idea_id']==id]
            shares.sort(key=lambda c:c.shared_at)
            store.local.register(id,shares[0] if shares else None,
                {key:idea.get(key) for key in ('personal_notes','favorite','stage')},
                canonical_url=idea['canonical_url'],saved_at=shares[0].shared_at.isoformat() if shares else idea['created_at'])
            for share in shares:
                store.local.add_share(id,share)
            with outbox.lock,outbox.db:
                queued=outbox.db.execute("select capture from jobs where idea_id=? or (idea_id is null and json_extract(capture,'$.canonical_url')=?)",(id,idea['canonical_url'])).fetchall()
                for row in queued:
                    store.local.add_share(id,SourceCapture.model_validate_json(row[0]))
                outbox.db.execute("update jobs set idea_id=? where idea_id is null and json_extract(capture,'$.canonical_url')=?",(id,idea['canonical_url']))
                cached=outbox.db.execute("select cached_result from jobs where idea_id=? and cached_result is not null and state in ('pending','processing') order by rowid limit 1",(id,)).fetchone()
            shares=[SourceCapture.model_validate(x) for x in store.local.shares(id)]
            published=store.local.get(id)
            # After a successful import/regeneration, a rerun must not roll back to an older cloud brief.
            if not published['published_hash'] or cached:
                store.publish_payload(id,json.loads(cached[0]) if cached else stored_payload(directory,data,idea))
            else:
                store.publish_payload(id,published['payload'])
            record=store.local.get(id)
            entry.update({'state':'migrated','page_id':record['page_id'],'url':'https://www.notion.so/'+record['page_id'].replace('-',''),
                          'content_hash':record['published_hash'],'source_shares':len(shares),
                          'images':len(record['payload'].get('image_uploads',[]))})
            if idea.get('retry_request_id') and shares:
                request_id=store.local.request_refresh(id,idea['retry_request_id'],idea.get('retry_requested_at'))
                request=RetryRequest(id=request_id,idea_id=id,capture=shares[0],requested_at=idea['retry_requested_at'])
                outbox.enqueue_retry(request)
                report['pending_requests_imported']+=1
            elif idea['processing_status'] in ('queued','processing') and shares:
                with outbox.lock,outbox.db:
                    existing=outbox.db.execute("select 1 from jobs where idea_id=? and state in ('pending','processing')",(id,)).fetchone()
                    if not existing:
                        outbox._insert(shares[0],'migration:resume:'+id,id)
            report['migrated']+=1
        except (PublicationError,ValueError,OSError,KeyError) as error:
            entry.update({'state':'skipped','reason':getattr(error,'code','migration_invalid_record')})
            report['skipped']+=1
        report['entries'].append(entry)
        private_write(directory/'migration-report.json',json.dumps(report,indent=2))
    report['pending_local_jobs']=outbox.pending_count()
    report['verification']['import_used_stored_content']=True
    private_write(directory/'migration-report.json',json.dumps(report,indent=2))
    return report


def local_status(settings):
    path=settings.data_dir/'outbox.sqlite'
    if not path.exists():
        return {'backend':settings.publishing_backend,'jobs':{},'library_entries':0}
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        result={'backend':settings.publishing_backend,
                'jobs':dict(db.execute('select state,count(*) from jobs group by state')),
                'pending_errors':dict(db.execute("select coalesce(error_code,'none'),count(*) from jobs where state in ('pending','processing') group by error_code"))}
        tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        if 'local_ideas' in tables:
            result['library_entries']=db.execute('select count(*) from local_ideas').fetchone()[0]
            result['published_entries']=db.execute("select count(*) from local_ideas where json_extract(record,'$.published_hash') is not null").fetchone()[0]
            result['publication_errors']=dict(db.execute("select json_extract(record,'$.publication_error'),count(*) from local_ideas where json_extract(record,'$.publication_error') is not null group by 1"))
            row=db.execute("select value from local_status where key='collector'").fetchone()
            result['collector']=json.loads(row[0]) if row else None
        return result
    finally:
        db.close()
