"""Private durable identities and generated snapshots share the existing outbox lock."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .outbox import synchronized
from .notion_api import PublicationError


class LocalLibrary:
    def __init__(self,outbox):
        self.db,self.lock=outbox.db,outbox.lock
        with self.lock,self.db:
            self.db.executescript('''
              create table if not exists local_ideas(id text primary key,canonical_url text not null unique,record text not null);
              create table if not exists local_shares(key text primary key,idea_id text not null,capture text not null);
              create table if not exists notion_requests(id text primary key,idea_id text not null,state text not null,requested_at text not null);
              create table if not exists local_status(key text primary key,value text not null);
            ''')

    @synchronized
    def get(self,id):
        row=self.db.execute('select record from local_ideas where id=?',(id,)).fetchone()
        if not row:
            raise PublicationError('local_identity_missing')
        return json.loads(row[0])

    @synchronized
    def put(self,record):
        encoded=json.dumps(record,ensure_ascii=False)
        if len(encoded.encode())>3*1024*1024:
            raise PublicationError('local_snapshot_limit')
        with self.db:
            self.db.execute('update local_ideas set record=? where id=?',(encoded,record['id']))

    @synchronized
    def register(self,id,capture=None,initial=None,*,canonical_url=None,saved_at=None):
        id=str(UUID(id)); url=capture.canonical_url if capture else canonical_url
        if not url:
            raise PublicationError('local_source_missing')
        row=self.db.execute('select id from local_ideas where canonical_url=?',(url,)).fetchone()
        if row and row[0]!=id:
            raise PublicationError('local_identity_conflict')
        existing=self.db.execute('select canonical_url from local_ideas where id=?',(id,)).fetchone()
        if existing and existing[0]!=url:
            raise PublicationError('local_identity_conflict')
        record={'id':id,'canonical_url':url,'saved_at':saved_at or (capture.shared_at.isoformat() if capture else None),
                'initial':initial or {},'payload':{},'page_id':None,'published_hash':None,'revision':None,'retired':[],
                'create_intent':False,'publication_error':None,'uploads':{}}
        with self.db:
            self.db.execute('insert or ignore into local_ideas values(?,?,?)',(id,url,json.dumps(record)))
        if capture:
            self.add_share(id,capture)
        return id

    @synchronized
    def ingest(self,capture):
        row=self.db.execute('select id from local_ideas where canonical_url=?',(capture.canonical_url,)).fetchone()
        id=row[0] if row else self.register(str(uuid4()),capture)
        self.add_share(id,capture)
        return id

    @synchronized
    def add_share(self,id,capture):
        key=hashlib.sha256(f'{capture.channel_id}:{capture.message_id}:{capture.original_url}'.encode()).hexdigest()
        with self.db:
            self.db.execute('insert or ignore into local_shares values(?,?,?)',(key,id,capture.model_dump_json()))
            record=self.get(id)
            if not record['saved_at'] or capture.shared_at<datetime.fromisoformat(record['saved_at'].replace('Z','+00:00')):
                record['saved_at']=capture.shared_at.isoformat()
                self.put(record)

    @synchronized
    def shares(self,id):
        return [json.loads(row[0]) for row in self.db.execute('select capture from local_shares where idea_id=? order by json_extract(capture,\'$.shared_at\'),key',(id,))]

    @synchronized
    def save_payload(self,id,payload):
        if len(json.dumps(payload).encode())>2*1024*1024:
            raise PublicationError('local_snapshot_limit')
        record=self.get(id)
        record['payload']={**record['payload'],**payload}
        self.put(record)
        return record

    @synchronized
    def all(self):
        return [json.loads(r[0]) for r in self.db.execute('select record from local_ideas order by rowid')]

    @synchronized
    def request_refresh(self,id,request_id=None,requested_at=None):
        row=self.db.execute("select id from notion_requests where idea_id=? and state='pending' order by rowid limit 1",(id,)).fetchone()
        if row:
            return row[0]
        request_id=request_id or str(uuid4())
        with self.db:
            self.db.execute('insert or ignore into notion_requests values(?,?,?,?)',(request_id,id,'pending',requested_at or datetime.now(timezone.utc).isoformat()))
        return request_id

    @synchronized
    def pending_requests(self):
        return [dict(r) for r in self.db.execute("select * from notion_requests where state='pending' order by rowid")]

    @synchronized
    def acknowledge(self,id,request_id):
        with self.db:
            self.db.execute("update notion_requests set state='complete' where id=? and idea_id=?",(request_id,id))

    @synchronized
    def status(self,key,value):
        with self.db:
            self.db.execute('insert into local_status values(?,?) on conflict(key) do update set value=excluded.value',(key,json.dumps(value)))
