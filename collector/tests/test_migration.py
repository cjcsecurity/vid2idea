import copy
import json
from datetime import datetime,timezone
from uuid import uuid4

from vid2idea.migration import inventory, import_backup, private_write
from vid2idea.outbox import Outbox
from vid2idea.notion_store import NotionStore
from test_notion import capture,payload,settings
from test_notion_store import FakeNotion


def backup(tmp_path,*,pending=False):
    path=tmp_path/'backup'; path.mkdir(mode=0o700)
    id=str(uuid4()); owner=str(uuid4()); p=payload()
    idea={'id':id,'owner_id':owner,'canonical_url':capture().canonical_url,**p,
        'personal_notes':'n'*20000,'favorite':True,'stage':'trying',
        'created_at':'2026-10-02T00:00:00Z','retry_request_id':str(uuid4()) if pending else None,
        'retry_requested_at':'2026-10-05T00:00:00Z' if pending else None,'images':[]}
    share={**capture().model_dump(mode='json'),'idea_id':id,'owner_id':owner}
    share.pop('canonical_url')
    private_write(path/'cloud.json',json.dumps({'format':1,'owner_id':owner,'ideas':[idea],'source_shares':[share],'collector_status':[],'images':[]}))
    return path,idea


def test_dry_run_has_no_writes_and_inventory_preserves_personal_values(tmp_path):
    path,idea=backup(tmp_path,pending=True)
    report=inventory(path)
    assert report['ideas']==1 and report['pending_cloud_requests']==1
    assert report['notes_characters']==20000 and report['favorites']==1 and report['images']==0
    box=Outbox(tmp_path/'jobs.sqlite'); api=FakeNotion(); s=settings(); api.data_source_id=s.notion_library_data_source_id
    cloud=NotionStore(s,box,api=api)
    result=import_backup(path,cloud,box,dry_run=True)
    assert result['dry_run'] and api.create_calls==0 and cloud.local.all()==[]
    box.close()


def test_import_and_rerun_preserve_uuid_user_edits_and_pending_jobs(tmp_path):
    path,idea=backup(tmp_path,pending=True)
    box=Outbox(tmp_path/'jobs.sqlite'); api=FakeNotion(); s=settings(); api.data_source_id=s.notion_library_data_source_id
    cloud=NotionStore(s,box,api=api)
    report=import_backup(path,cloud,box)
    assert report['migrated']==1 and report['model_calls']==0 and box.pending_count()==1
    record=cloud.local.get(idea['id']); page=api.pages[record['page_id']]
    assert page['properties']['Saved at']['date']['start']==capture().shared_at.isoformat()
    assert page['properties']['Favorite']['checkbox']
    assert len(''.join(x['text']['content'] for x in page['properties']['Personal notes']['rich_text']))==20000
    page['properties']['Favorite']={'checkbox':False}
    page['properties']['Personal notes']={'rich_text':[{'text':{'content':'Edited in Notion'}}]}
    before=copy.deepcopy(page['properties'])
    report=import_backup(path,cloud,box)
    assert report['migrated']==1 and api.create_calls==1 and box.pending_count()==1
    assert page['properties']==before
    assert record['id']==idea['id'] and len(cloud.local.shares(idea['id']))==1
    box.close()


def test_locally_queued_duplicate_is_imported_into_provenance_before_job_completes(tmp_path):
    from vid2idea.worker import Worker
    path,idea=backup(tmp_path)
    box=Outbox(tmp_path/'jobs.sqlite'); api=FakeNotion(); s=settings(); api.data_source_id=s.notion_library_data_source_id
    queued=capture(message='1222222222222222229').model_copy(update={'note':'Local queue note'})
    box.enqueue([queued],queued.channel_id,queued.message_id)
    cloud=NotionStore(s,box,api=api)
    import_backup(path,cloud,box)
    def processor(*args): raise AssertionError('Duplicate must reuse the imported article')
    assert Worker(box,cloud,s,processor=processor).run_once()=='processed'
    shares=cloud.local.shares(idea['id'])
    assert len(shares)==2 and any(x['note']=='Local queue note' for x in shares)
    assert box.cursor(queued.channel_id)==queued.message_id
    box.close()
