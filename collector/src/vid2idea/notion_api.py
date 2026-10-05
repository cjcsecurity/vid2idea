"""Bounded REST transport; uncertain writes are reconciled by the durable publisher."""
import json
import math
import threading
import time
from uuid import UUID

import httpx


class PublicationError(Exception):
    def __init__(self, code, *, retry_after=60, uncertain=False, committed_ids=None, committed_resource_id=None):
        super().__init__(code)
        self.code=code
        self.retry_after=retry_after
        self.uncertain=uncertain
        self.committed_ids=committed_ids or []
        self.committed_resource_id=committed_resource_id


SCHEMA = {'Name':'title','Origin':'select','Source URL':'url','Summary':'rich_text',
    'Topics':'multi_select','Last published':'date','Processing status':'select','Error code':'rich_text',
    'External ID':'rich_text','Content hash':'rich_text','Kind':'select','Saved at':'date',
    'Projects':'relation','Review status':'select','Stage':'select','Favorite':'checkbox',
    'Personal notes':'rich_text','Refresh article':'checkbox'}


class NotionAPI:
    def __init__(self, settings, *, transport=None, interval=0.5):
        self.data_source_id=str(UUID(settings.notion_library_data_source_id)) if settings.notion_library_data_source_id else ''
        self.projects_id=str(UUID(settings.notion_projects_data_source_id)) if settings.notion_projects_data_source_id else ''
        self.client=httpx.Client(base_url='https://api.notion.com/v1', timeout=httpx.Timeout(30,connect=10),
            headers={'Authorization':'Bearer '+settings.notion_api_token.get_secret_value(),
                     'Notion-Version':'2026-03-11'},transport=transport,follow_redirects=False)
        self.lock=threading.RLock()
        self.interval=interval
        self.next_request=0
        self.backoff_until=0
        self._bot_id=None
        self.validated=False

    def request(self, method, path, **kwargs):
        if not path.startswith('/') or '://' in path or '..' in path:
            raise PublicationError('notion_invalid_endpoint')
        if 'json' in kwargs and len(json.dumps(kwargs['json'],ensure_ascii=False).encode())>480000:
            raise PublicationError('notion_payload_limit')
        with self.lock:
            now=time.monotonic()
            if now<self.backoff_until:
                raise PublicationError('notion_rate_limited',retry_after=math.ceil(self.backoff_until-now))
            time.sleep(max(0,self.next_request-now))
            self.next_request=time.monotonic()+self.interval
            try:
                response=self.client.request(method,path,**kwargs)
            except httpx.HTTPError:
                raise PublicationError('notion_unavailable',uncertain=method not in ('GET','DELETE')) from None
            try:
                data=response.json()
            except ValueError:
                data={}
            if response.is_success:
                return data
            extra=data.get('additional_data',{}) if isinstance(data,dict) else {}
            try:
                delay=max(1,int(response.headers.get('Retry-After',extra.get('retry_after',60))))
            except (ValueError,TypeError):
                delay=60
            status=response.status_code
            if status in (429,529):
                self.backoff_until=time.monotonic()+delay
            code={401:'notion_authentication',403:'notion_access',404:'notion_missing',
                  400:'notion_invalid_request',409:'notion_conflict',429:'notion_rate_limited'}.get(status,'notion_unavailable')
            if status==429 and extra.get('rate_limit_reason')=='public_api_request_blocked':
                code='notion_api_restricted'
            if status==403 and 'block limit' in str(data.get('message','')).lower():
                code='notion_workspace_limit'
            raise PublicationError(code,retry_after=delay,uncertain=status>=500 and status!=529 and method not in ('GET','DELETE'),
                committed_ids=extra.get('committed_child_ids'),committed_resource_id=extra.get('committed_resource_id'))

    @property
    def bot_id(self):
        if self._bot_id is None:
            self._bot_id=self.request('GET','/users/me')['id']
        return self._bot_id

    def validate_schema(self):
        if not self.data_source_id or not self.projects_id:
            raise PublicationError('notion_invalid_configuration')
        schema=self.request('GET',f'/data_sources/{self.data_source_id}')
        props=schema.get('properties',{})
        if any(props.get(name,{}).get('type')!=kind for name,kind in SCHEMA.items()):
            raise PublicationError('notion_schema_mismatch',retry_after=300)
        expected={'Origin':{'Manual','Codex','vid2idea'},'Kind':{'Article'},
                  'Stage':{'Saved','Trying','Done'},'Review status':{'Unread','Reviewed','Archived'},
                  'Processing status':{'Queued','Processing','Ready','Partial','Blocked','Failed'}}
        for name,options in expected.items():
            if not options<={x['name'] for x in props[name]['select'].get('options',[])}:
                raise PublicationError('notion_schema_mismatch',retry_after=300)
        if str(UUID(props['Projects']['relation']['data_source_id']))!=self.projects_id:
            raise PublicationError('notion_schema_mismatch',retry_after=300)
        self.request('GET',f'/data_sources/{self.projects_id}')
        self.validated=True

    def query(self, filter, *, include_archived=False):
        result=[]
        for archived in ([False,True] if include_archived else [False]):
            cursor=None
            while True:
                body={'filter':filter,'page_size':100,'is_archived':archived}
                if cursor:
                    body['start_cursor']=cursor
                data=self.request('POST',f'/data_sources/{self.data_source_id}/query',json=body)
                result.extend(data['results'])
                if not data.get('has_more'):
                    break
                cursor=data['next_cursor']
        return result

    def validate_project(self, page_id):
        page_id = str(UUID(page_id))
        page = self.request('GET', f'/pages/{page_id}')
        if page.get('archived') or page.get('in_trash'):
            raise PublicationError('notion_project_unavailable')
        parent = page.get('parent', {})
        if parent.get('type') != 'data_source_id' or parent.get('data_source_id', '').replace('-', '') != self.projects_id.replace('-', ''):
            raise PublicationError('notion_project_mismatch')

    def children(self, parent):
        result=[]; cursor=None
        while True:
            params={'page_size':100}
            if cursor:
                params['start_cursor']=cursor
            data=self.request('GET',f'/blocks/{parent}/children',params=params)
            result.extend(data['results'])
            if not data.get('has_more'):
                return result
            cursor=data['next_cursor']

    def close(self):
        self.client.close()
