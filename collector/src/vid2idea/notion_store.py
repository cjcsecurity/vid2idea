"""Notion publisher backed by local durable identity, revision, and request journals."""
import base64
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from .cloud import validate_publication
from .local_library import LocalLibrary
from .models import SourceCapture, RetryRequest
from .notion_api import NotionAPI, PublicationError
from .notion_content import block, page_properties, render_article, rich_text


def text_value(property):
    return ''.join(x.get('plain_text',x.get('text',{}).get('content','')) for x in property.get('rich_text',[]))


def signature(item):
    kind=item['type']; body=item.get(kind,{})
    parts=body.get('caption' if kind=='image' else 'rich_text',[])
    return kind,tuple((x.get('text',{}).get('content',x.get('plain_text','')),x.get('text',{}).get('link')) for x in parts)


class NotionStore:
    def __init__(self,settings,outbox,*,api=None):
        self.settings=settings
        self.local=LocalLibrary(outbox)
        self.outbox=outbox
        self.api=api or NotionAPI(settings)
        self.poll_error=None

    def ingest(self,capture):
        return self.local.ingest(capture)

    def status(self,id,status,code=None):
        if str(status)=='processing' and self.local.get(id)['revision']:
            # Finish a cached publication before allowing another generation for this identity.
            raise PublicationError('notion_publication_pending')
        self.local.save_payload(id,{'processing_status':str(status),'error_code':code})

    def is_finished(self,id):
        record=self.local.get(id)
        # A generated snapshot can still be waiting for remote publication. Its
        # original cached job owns that work; a duplicate must not generate again.
        return bool(record['payload'].get('brief') and record['payload'].get('processing_status') in ('ready','partial'))

    def _check_page(self,record,page):
        if page.get('in_trash') or page.get('archived'):
            raise PublicationError('notion_page_trashed',retry_after=300)
        if text_value(page['properties'].get('External ID',{}))!='vid2idea:idea:'+record['id']:
            raise PublicationError('notion_identity_conflict',retry_after=300)
        parent=page.get('parent',{})
        if parent.get('data_source_id') and UUID(parent['data_source_id'])!=UUID(self.api.data_source_id):
            raise PublicationError('notion_destination_conflict',retry_after=300)

    def _ensure_page(self,record):
        if record['page_id']:
            page=self.api.request('GET',f"/pages/{record['page_id']}")
            self._check_page(record,page)
            return page
        pages=self.api.query({'property':'External ID','rich_text':{'equals':'vid2idea:idea:'+record['id']}},include_archived=True)
        if len(pages)>1:
            raise PublicationError('notion_identity_conflict',retry_after=300)
        if pages:
            page=pages[0]
            self._check_page(record,page)
            record['page_id']=page['id']; record['create_intent']=False
            self.local.put(record)
            return page
        if record['create_intent']:
            raise PublicationError('notion_create_reconciliation',retry_after=300)
        record['create_intent']=True
        self.local.put(record)
        try:
            page=self.api.request('POST','/pages',json={
                'parent':{'type':'data_source_id','data_source_id':self.api.data_source_id},
                'properties':page_properties(record,record['payload'],create=True,
                    project_page_id=self.settings.notion_vid2idea_project_page_id)})
        except PublicationError as error:
            if error.committed_resource_id:
                record['page_id']=error.committed_resource_id
            elif not error.uncertain:
                record['create_intent']=False
            self.local.put(record)
            raise
        record['page_id']=page['id']; record['create_intent']=False
        self.local.put(record)
        return page

    def _append(self,record,name,parent,children):
        revision=record['revision']; ops=revision.setdefault('ops',{})
        operation=ops.get(name)
        if operation and operation.get('done'):
            return operation['ids']
        if operation:
            if operation.get('ids'):
                recovered=[self.api.request('GET',f'/blocks/{id}') for id in operation['ids']]
            else:
                recovered=[b for b in self.api.children(parent) if b['id'] not in operation['baseline']
                           and b.get('created_by',{}).get('id')==self.api.bot_id]
            if len(recovered)!=len(children) or [signature(b) for b in recovered]!=[signature(b) for b in children]:
                raise PublicationError('notion_append_reconciliation',retry_after=300)
            operation['ids']=[b['id'] for b in recovered]; operation['done']=True
            self.local.put(record)
            return operation['ids']
        operation={'baseline':[b['id'] for b in self.api.children(parent)],'ids':[],'done':False}
        ops[name]=operation
        self.local.put(record)
        try:
            response=self.api.request('PATCH',f'/blocks/{parent}/children',json={'children':children})
        except PublicationError as error:
            if error.committed_ids:
                operation['ids']=error.committed_ids
            elif not error.uncertain:
                del ops[name]
            self.local.put(record)
            raise
        operation['ids']=[b['id'] for b in response['results']]
        if len(operation['ids'])!=len(children):
            self.local.put(record)
            raise PublicationError('notion_append_reconciliation',retry_after=300)
        operation['done']=True
        self.local.put(record)
        return operation['ids']

    def _images(self,record):
        images=record['payload'].get('image_uploads',[])
        if not isinstance(images,list) or len(images)>3:
            raise PublicationError('local_invalid_images')
        ids=[]
        for image in images:
            try:
                data=base64.b64decode(image['data'],validate=True)
                sha=hashlib.sha256(data).hexdigest()
                valid=data.startswith(b'\xff\xd8\xff') and len(data)<=204800 and sha==image['sha256']
            except (KeyError,ValueError,TypeError):
                valid=False
            if not valid:
                raise PublicationError('local_invalid_images')
            upload=record['uploads'].get(sha)
            if upload and not upload.get('attached'):
                remote=self.api.request('GET',f"/file_uploads/{upload['id']}")
                if remote['status'] in ('expired','failed'):
                    upload=None
                elif remote['status']=='uploaded':
                    upload['uploaded']=True
                    self.local.put(record)
            if not upload:
                remote=self.api.request('POST','/file_uploads',json={'mode':'single_part','filename':sha+'.jpg','content_type':'image/jpeg'})
                upload={'id':remote['id'],'uploaded':False,'attached':False}
                record['uploads'][sha]=upload
                self.local.put(record)
            if not upload['uploaded']:
                self.api.request('POST',f"/file_uploads/{upload['id']}/send",files={'file':(sha+'.jpg',data,'image/jpeg')})
                upload['uploaded']=True
                self.local.put(record)
            ids.append(upload['id'])
        return ids

    def _cleanup(self,record):
        for retired in list(record['retired']):
            try:
                root=self.api.request('GET',f"/blocks/{retired['root']}")
            except PublicationError as error:
                if error.code!='notion_missing':
                    raise
                root={'in_trash':True}
            if root.get('in_trash'):
                record['retired'].remove(retired)
                self.local.put(record)
                continue
            for id in list(retired['ids']):
                try:
                    item=self.api.request('GET',f'/blocks/{id}')
                except PublicationError as error:
                    if error.code!='notion_missing':
                        raise
                    item={'in_trash':True}
                # Preserve a generated block that has acquired user descendants.
                if not item.get('in_trash') and not item.get('has_children'):
                    self.api.request('DELETE',f'/blocks/{id}')
                retired['ids'].remove(id)
                self.local.put(record)
            remaining=self.api.children(retired['root'])
            if remaining:
                self.api.request('PATCH',f"/blocks/{retired['root']}",json={'callout':{'rich_text':rich_text('Additional notes')}})
            else:
                self.api.request('DELETE',f"/blocks/{retired['root']}")
            record['retired'].remove(retired)
            self.local.put(record)

    def publish_payload(self,id,payload):
        validate_publication({k:v for k,v in payload.items() if k!='image_uploads'})
        record=self.local.save_payload(id,payload)
        try:
            self._publish(record)
        except PublicationError as error:
            record['publication_error']=error.code
            self.local.put(record)
            raise

    def _publish(self,record):
        if not self.api.validated:
            self.api.validate_schema()
        self._ensure_page(record)
        self._cleanup(record)
        shares=record['revision']['shares'] if record['revision'] else self.local.shares(record['id'])
        hash=hashlib.sha256(json.dumps({'payload':record['payload'],'shares':shares},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if record['published_hash']==hash and not record['revision']:
            record['publication_error']=None; self.local.put(record)
            return
        if record['revision'] and record['revision']['hash']!=hash:
            raise PublicationError('notion_revision_conflict')
        if not record['revision']:
            record['revision']={'hash':hash,'root':None,'ops':{},'shares':shares}
            self.local.put(record)
        revision=record['revision']
        ids=self._images(record)
        if not revision['root']:
            root=block('callout','Article update in progress')
            revision['root']=self._append(record,'root',record['page_id'],[root])[0]
            self.local.put(record)
        children=render_article(record['payload'],shares[:20],ids)
        if len(shares)>20:
            children.append(block('paragraph',f'{len(shares)-20} additional source shares are preserved in the local library ledger.'))
        owned=[]
        for index in range(0,len(children),25):
            owned.extend(self._append(record,'body:'+str(index),revision['root'],children[index:index+25]))
            attached={b['image']['file_upload']['id'] for b in children[index:index+25] if b['type']=='image'}
            for upload in record['uploads'].values():
                if upload['id'] in attached:
                    upload['attached']=True
            self.local.put(record)
        self.api.request('PATCH',f"/blocks/{revision['root']}",json={'callout':{'rich_text':rich_text('Article')}})
        self.api.request('PATCH',f"/pages/{record['page_id']}",json={'properties':page_properties(record,record['payload'],content_hash=hash)})
        if record.get('current_root'):
            record['retired'].append({'root':record['current_root'],'ids':record['owned_ids']})
        record['current_root']=revision['root']; record['owned_ids']=owned
        record['published_hash']=hash; record['revision']=None; record['publication_error']=None
        self.local.put(record)
        self._cleanup(record)
        active={image['sha256'] for image in record['payload'].get('image_uploads',[])}
        record['uploads']={sha:value for sha,value in record['uploads'].items() if sha in active}
        self.local.put(record)

    def list_retry_requests(self):
        try:
            pages=self.api.query({'and':[{'property':'Origin','select':{'equals':'vid2idea'}},
                                        {'property':'Refresh article','checkbox':{'equals':True}}]})
            for page in pages:
                external=text_value(page['properties'].get('External ID',{}))
                if not external.startswith('vid2idea:idea:'):
                    continue
                id=external.removeprefix('vid2idea:idea:')
                try:
                    record=self.local.get(id)
                except PublicationError:
                    continue
                self._check_page(record,page)
                if record['page_id']!=page['id']:
                    raise PublicationError('notion_identity_conflict')
                if self.local.shares(id):
                    self.local.request_refresh(id)
            self.poll_error=None
        except PublicationError as error:
            self.poll_error=error.code
            self.local.status('refresh_poll',{'error_code':error.code,'at':datetime.now(timezone.utc).isoformat()})
        result=[]
        for request in self.local.pending_requests():
            shares=self.local.shares(request['idea_id'])
            if shares:
                result.append(RetryRequest(id=request['id'],idea_id=request['idea_id'],
                    capture=SourceCapture.model_validate(shares[0]),requested_at=request['requested_at']))
        return result

    def acknowledge_retry(self,id,request_id):
        pending=[r for r in self.local.pending_requests() if r['id']==request_id and r['idea_id']==id]
        if not pending:
            return
        record=self.local.get(id)
        self._check_page(record,self.api.request('GET',f"/pages/{record['page_id']}"))
        self.api.request('PATCH',f"/pages/{record['page_id']}",json={'properties':{'Refresh article':{'checkbox':False}}})
        self.local.acknowledge(id,request_id)

    def record_status(self,pending_count,last_error_code=None):
        self.local.status('collector',{'last_seen_at':datetime.now(timezone.utc).isoformat(),
            'pending_count':pending_count,'last_error_code':last_error_code or self.poll_error,'backend':'notion'})


def make_store(settings,outbox):
    if settings.publishing_backend=='notion':
        return NotionStore(settings,outbox)
    from .cloud import CloudStore
    return CloudStore(settings)
