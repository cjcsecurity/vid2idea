import copy
import base64
import hashlib
import json
from uuid import uuid4

import pytest

from vid2idea.notion_api import PublicationError
from vid2idea.notion_store import NotionStore
from vid2idea.outbox import Outbox
from test_notion import capture, payload, settings


class FakeNotion:
    def __init__(self):
        self.data_source_id=None; self.bot_id='dedicated-bot'; self.validated=True
        self.pages={}; self.blocks={}; self.by_parent={}; self.files={}
        self.create_calls=0; self.append_calls=0; self.fail_create=None; self.fail_append=False
        self.fail_ack=False; self.unavailable=False

    def validate_schema(self):
        self.validated=True

    def children(self,parent):
        return [copy.deepcopy(self.blocks[id]) for id in self.by_parent.get(parent,[]) if not self.blocks[id].get('in_trash')]

    def query(self,filter,**kwargs):
        def matches(page,rule):
            if 'and' in rule:
                return all(matches(page,x) for x in rule['and'])
            name=rule['property']; value=page['properties'].get(name,{})
            if 'rich_text' in rule:
                return ''.join(x['text']['content'] for x in value.get('rich_text',[]))==rule['rich_text']['equals']
            if 'checkbox' in rule:
                return value.get('checkbox',False)==rule['checkbox']['equals']
            return value.get('select',{}).get('name')==rule['select']['equals']
        if self.unavailable:
            raise PublicationError('notion_unavailable')
        return [copy.deepcopy(p) for p in self.pages.values() if not p.get('in_trash') and matches(p,filter)]

    def request(self,method,path,**kw):
        if self.unavailable:
            raise PublicationError('notion_unavailable')
        body=kw.get('json',{})
        if method=='POST' and path=='/pages':
            self.create_calls+=1
            if self.fail_create=='rejected':
                self.fail_create=None
                raise PublicationError('notion_access')
            id=str(uuid4()); page={'id':id,'properties':copy.deepcopy(body['properties']),
                'parent':body['parent'],'in_trash':False,'url':'https://notion.so/'+id}
            self.pages[id]=page
            if self.fail_create=='committed':
                self.fail_create=None
                raise PublicationError('notion_unavailable',uncertain=True)
            return copy.deepcopy(page)
        if path.startswith('/pages/'):
            id=path.split('/')[2]; page=self.pages[id]
            if method=='PATCH':
                if self.fail_ack and 'Refresh article' in body.get('properties',{}):
                    self.fail_ack=False
                    raise PublicationError('notion_unavailable')
                page['properties'].update(copy.deepcopy(body.get('properties',{})))
            return copy.deepcopy(page)
        if path.endswith('/children') and method=='PATCH':
            self.append_calls+=1; parent=path.split('/')[2]; result=[]
            for b in body['children']:
                id=str(uuid4()); block={**copy.deepcopy(b),'id':id,'created_by':{'id':self.bot_id},'has_children':False,'in_trash':False}
                self.blocks[id]=block; self.by_parent.setdefault(parent,[]).append(id); result.append(block)
            if self.fail_append:
                self.fail_append=False
                raise PublicationError('notion_unavailable',uncertain=True)
            return {'results':copy.deepcopy(result)}
        if path.startswith('/blocks/'):
            id=path.split('/')[2]; b=self.blocks[id]
            if method=='DELETE':
                b['in_trash']=True
            elif method=='PATCH':
                b.update(copy.deepcopy(body))
            return copy.deepcopy(b)
        if method=='POST' and path=='/file_uploads':
            id=str(uuid4()); self.files[id]={'id':id,'status':'pending'}
            return self.files[id]
        if path.startswith('/file_uploads/'):
            id=path.split('/')[2]
            if path.endswith('/send'):
                self.files[id]['status']='uploaded'
            return self.files[id]
        raise AssertionError((method,path))


def store(tmp_path,api=None):
    box=Outbox(tmp_path/'outbox.sqlite'); api=api or FakeNotion(); s=settings(); api.data_source_id=s.notion_library_data_source_id
    return box,NotionStore(s,box,api=api),api


def test_uncertain_create_and_restart_reuse_exact_page(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); api.fail_create='committed'
    with pytest.raises(PublicationError):
        cloud.publish_payload(id,payload())
    box.close(); box=Outbox(tmp_path/'outbox.sqlite'); cloud=NotionStore(settings(),box,api=api)
    cloud.publish_payload(id,payload())
    assert api.create_calls==1 and len(api.pages)==1
    assert cloud.is_finished(id)
    box.close()


def test_uncertain_append_reconciles_without_duplicate_blocks(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); api.fail_append=True
    with pytest.raises(PublicationError):
        cloud.publish_payload(id,payload())
    cloud.publish_payload(id,payload())
    record=cloud.local.get(id)
    assert api.create_calls==1
    assert len(api.children(record['page_id']))==1
    assert len(api.children(record['current_root']))==len(record['owned_ids'])
    box.close()


def test_refresh_preserves_properties_and_arbitrary_user_blocks(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); cloud.publish_payload(id,payload())
    record=cloud.local.get(id); page=api.pages[record['page_id']]
    custom={'Personal notes':{'rich_text':[{'text':{'content':'x'*2000}}]*10},'Favorite':{'checkbox':True},
            'Stage':{'select':{'name':'Trying'}},'Projects':{'relation':[{'id':str(uuid4())}]}}
    page['properties'].update(copy.deepcopy(custom))
    user={'id':'human-block','type':'paragraph','paragraph':{'rich_text':[{'text':{'content':'Keep this'}}]},'created_by':{'id':'human'}}
    api.blocks['human-block']=user; api.by_parent[record['current_root']].append('human-block')
    api.blocks['top-level']=dict(user,id='top-level'); api.by_parent[record['page_id']].append('top-level')
    page['properties']['Refresh article']={'checkbox':True}
    requests=cloud.list_retry_requests(); assert len(requests)==1
    assert cloud.list_retry_requests()[0].id==requests[0].id
    p=payload(); p['brief']['summary']='A revised project.'
    cloud.publish_payload(id,p); cloud.acknowledge_retry(id,requests[0].id)
    assert all(page['properties'][k]==v for k,v in custom.items())
    assert not page['properties']['Refresh article']['checkbox']
    assert not api.blocks['human-block'].get('in_trash') and not api.blocks['top-level'].get('in_trash')
    assert len(api.pages)==1
    box.close()


def test_mapped_trashed_page_is_not_recreated(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); cloud.publish_payload(id,payload())
    api.pages[cloud.local.get(id)['page_id']]['in_trash']=True
    with pytest.raises(PublicationError,match='notion_page_trashed'):
        cloud.publish_payload(id,payload())
    assert api.create_calls==1
    box.close()


def test_ack_failure_retries_without_republishing_content(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); cloud.publish_payload(id,payload())
    page=api.pages[cloud.local.get(id)['page_id']]; page['properties']['Refresh article']={'checkbox':True}
    request=cloud.list_retry_requests()[0]; before=api.append_calls; api.fail_ack=True
    with pytest.raises(PublicationError):
        cloud.acknowledge_retry(id,request.id)
    cloud.publish_payload(id,payload()); cloud.acknowledge_retry(id,request.id)
    assert api.append_calls==before and cloud.local.pending_requests()==[]
    box.close()


def test_outage_retains_result_and_retry_after_without_media_attempts(tmp_path, codex_available):
    from datetime import datetime,timezone,timedelta
    from vid2idea.worker import Worker
    box,cloud,api=store(tmp_path); calls=[]
    box.enqueue([capture()],capture().channel_id,capture().message_id)
    def processor(*args):
        calls.append(True); return payload()
    worker=Worker(box,cloud,settings(),processor=processor)
    api.unavailable=True; now=datetime.now(timezone.utc)
    assert worker.run_once(now)=='rescheduled'
    row=box.db.execute('select * from jobs').fetchone()
    assert row['error_code']=='notion_unavailable' and row['retry_count']==0
    assert json.loads(row['cached_result'])['brief']['summary']=='A useful project.'
    # New gateway/history captures can still commit during a publication outage.
    box.enqueue([capture('https://example.com/next',message='1222222222222222223')],capture().channel_id,'1222222222222222223')
    assert box.pending_count()==2 and box.cursor(capture().channel_id)=='1222222222222222223'
    api.unavailable=False
    assert worker.run_once(now+timedelta(minutes=2))=='processed'
    assert len(calls)==1 and len(api.pages)==1
    assert cloud.local.all()[0]['payload']['brief']['summary']=='A useful project.'
    box.close()


def test_image_upload_is_reused_on_resume_and_has_no_cloud_url(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); p=payload()
    data=b'\xff\xd8\xff' + b'test jpeg bytes'
    sha=hashlib.sha256(data).hexdigest()
    p['image_uploads']=[{'data':base64.b64encode(data).decode(),'sha256':sha,'caption':'Screenshot','timestamp_seconds':2}]
    api.fail_append=True
    with pytest.raises(PublicationError): cloud.publish_payload(id,p)
    cloud.publish_payload(id,p)
    assert len(api.files)==1 and list(api.files.values())[0]['status']=='uploaded'
    record=cloud.local.get(id)
    image=[b for b in api.children(record['current_root']) if b['type']=='image'][0]
    assert image['image']['type']=='file_upload'
    assert 'supabase' not in json.dumps(image)
    assert record['uploads'][sha]['attached']
    box.close()


def test_known_create_rejection_can_retry_after_credentials_fixed(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); api.fail_create='rejected'
    with pytest.raises(PublicationError,match='notion_access'): cloud.publish_payload(id,payload())
    assert not cloud.local.get(id)['create_intent']
    cloud.publish_payload(id,payload())
    assert len(api.pages)==1
    box.close()


def test_multiple_external_ids_conflict_without_creating(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); cloud.publish_payload(id,payload())
    record=cloud.local.get(id); page=api.pages[record['page_id']]
    duplicate=copy.deepcopy(page); duplicate['id']=str(uuid4()); api.pages[duplicate['id']]=duplicate
    record['page_id']=None; cloud.local.put(record)
    with pytest.raises(PublicationError,match='notion_identity_conflict'): cloud.publish_payload(id,payload())
    assert api.create_calls==1
    box.close()


def test_ambiguous_uncommitted_create_holds_without_duplicating(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); record=cloud.local.get(id)
    record['create_intent']=True; cloud.local.put(record)
    with pytest.raises(PublicationError,match='notion_create_reconciliation'): cloud.publish_payload(id,payload())
    assert api.create_calls==0
    box.close()


def test_pending_refresh_request_survives_restart_and_poll_outage(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); cloud.publish_payload(id,payload())
    api.pages[cloud.local.get(id)['page_id']]['properties']['Refresh article']={'checkbox':True}
    request=cloud.list_retry_requests()[0]
    box.close(); box=Outbox(tmp_path/'outbox.sqlite'); cloud=NotionStore(settings(),box,api=api)
    api.unavailable=True
    assert cloud.list_retry_requests()[0].id==request.id
    assert cloud.poll_error=='notion_unavailable'
    box.close()


def test_cleanup_recovers_when_root_deletion_commits_then_times_out(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); cloud.publish_payload(id,payload())
    old=cloud.local.get(id)['current_root']; original=api.request
    def request(method,path,**kw):
        result=original(method,path,**kw)
        if method=='DELETE' and path=='/blocks/'+old:
            api.request=original
            raise PublicationError('notion_unavailable')
        return result
    api.request=request; p=payload(); p['brief']['summary']='Updated'
    with pytest.raises(PublicationError): cloud.publish_payload(id,p)
    def children(parent):
        if api.blocks.get(parent,{}).get('in_trash'):
            raise PublicationError('notion_missing')
        return FakeNotion.children(api,parent)
    api.children=children
    cloud.publish_payload(id,p)
    assert cloud.local.get(id)['retired']==[] and len(api.pages)==1
    box.close()


def test_duplicate_during_unfinished_revision_coalesces_and_preserves_new_share(tmp_path, codex_available):
    from datetime import datetime,timezone,timedelta
    from vid2idea.worker import Worker
    from vid2idea.models import RetryRequest
    box,cloud,api=store(tmp_path); calls=[]; now=datetime.now(timezone.utc)
    box.enqueue([capture()],capture().channel_id,capture().message_id)
    def processor(*args): calls.append(True); return payload()
    worker=Worker(box,cloud,settings(),processor=processor); api.fail_append=True
    assert worker.run_once(now)=='rescheduled'
    id=cloud.local.all()[0]['id']
    duplicate=capture(message='1222222222222222222')
    box.enqueue([duplicate],duplicate.channel_id,duplicate.message_id)
    assert worker.run_once(now+timedelta(seconds=1))=='processed'
    assert len(calls)==1
    request_id=cloud.local.request_refresh(id)
    box.enqueue_retry(RetryRequest(id=request_id,idea_id=id,capture=capture(),requested_at=now))
    assert worker.run_once(now+timedelta(seconds=2))=='rescheduled'
    assert len(calls)==1
    assert worker.run_once(now+timedelta(minutes=2))=='processed'
    assert len(api.pages)==1 and len(cloud.local.shares(id))==2
    assert cloud.local.get(id)['revision'] is None
    box.close()


def test_only_committed_image_uploads_marked_attached_and_expired_upload_replaced(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); p=payload()
    p['brief']['resources']=[{'name':f'Resource {i}','url':f'https://example.com/{i}','summary':'Summary'} for i in range(7)]
    p['image_uploads']=[]
    for i in range(3):
        data=b'\xff\xd8\xff'+str(i).encode()
        p['image_uploads'].append({'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode(),'caption':str(i)})
    original=api.request
    def request(method,path,**kw):
        children=kw.get('json',{}).get('children',[])
        if method=='PATCH' and path.endswith('/children') and children and children[0]['type']=='image':
            raise PublicationError('notion_rate_limited')
        return original(method,path,**kw)
    api.request=request
    with pytest.raises(PublicationError): cloud.publish_payload(id,p)
    record=cloud.local.get(id); last=p['image_uploads'][2]['sha256']
    assert not record['uploads'][last]['attached']
    api.files[record['uploads'][last]['id']]['status']='expired'; api.request=original
    cloud.publish_payload(id,p)
    assert len(api.files)==4
    record=cloud.local.get(id)
    assert len([b for b in api.children(record['current_root']) if b['type']=='image'])==3
    assert all(x['attached'] for x in record['uploads'].values())
    box.close()


def test_callout_omits_nullable_icon_unsupported_by_live_api(tmp_path):
    box,cloud,api=store(tmp_path); id=cloud.ingest(capture()); original=api.request
    def request(method,path,**kw):
        for child in kw.get('json',{}).get('children',[]):
            if child['type']=='callout' and 'icon' in child['callout'] and child['callout']['icon'] is None:
                raise PublicationError('notion_invalid_request')
        return original(method,path,**kw)
    api.request=request
    cloud.publish_payload(id,payload())
    assert len(api.pages)==1
    box.close()
