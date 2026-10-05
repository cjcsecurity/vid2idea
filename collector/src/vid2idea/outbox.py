import hashlib
import json
import sqlite3
import threading
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel
from .models import SourceCapture, RetryRequest


class Job(BaseModel):
    id: str
    capture: SourceCapture
    state: str
    retry_count: int
    idea_id: str | None = None
    retry_request_id: str | None = None
    cached_result: dict | None = None


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapped


class Outbox:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('pragma journal_mode=WAL')
        self.db.executescript('''
          create table if not exists jobs (
            id text primary key, capture text not null, state text not null default 'pending',
            retry_count integer not null default 0, idea_id text, retry_request_id text,
            cached_result text, error_code text, next_attempt_at real not null default 0);
          create table if not exists cursors (channel_id text primary key, message_id text not null);
        ''')
        with self.db:
            self.db.execute("update jobs set state='pending' where state='processing'")

    @synchronized
    def close(self):
        self.db.close()

    def _insert(self, capture, key, idea_id=None, retry_request_id=None):
        self.db.execute('insert or ignore into jobs(id,capture,idea_id,retry_request_id) values(?,?,?,?)', (key, capture.model_dump_json(), idea_id, retry_request_id))

    @synchronized
    def enqueue(self, captures: list[SourceCapture], channel_id: str, last_message_id: str):
        with self.db:
            for capture in captures:
                key = hashlib.sha256(f'{capture.message_id}:{capture.original_url}'.encode()).hexdigest()
                self._insert(capture, key)
            self.db.execute('''insert into cursors values(?,?) on conflict(channel_id) do update set message_id=excluded.message_id
                where cast(excluded.message_id as integer)>cast(cursors.message_id as integer)''', (channel_id, last_message_id))

    @synchronized
    def enqueue_retry(self, request: RetryRequest):
        with self.db:
            self._insert(request.capture, 'retry:' + request.id, request.idea_id, request.id)

    @synchronized
    def cursor(self, channel_id):
        row = self.db.execute('select message_id from cursors where channel_id=?', (channel_id,)).fetchone()
        return row[0] if row else None

    @synchronized
    def claim(self, now: datetime) -> Job | None:
        with self.db:
            row = self.db.execute("select * from jobs where state='pending' and next_attempt_at<=? order by rowid limit 1", (now.timestamp(),)).fetchone()
            if not row:
                return None
            self.db.execute("update jobs set state='processing' where id=?", (row['id'],))
        return Job(id=row['id'], capture=SourceCapture.model_validate_json(row['capture']), state='processing', retry_count=row['retry_count'], idea_id=row['idea_id'], retry_request_id=row['retry_request_id'], cached_result=json.loads(row['cached_result']) if row['cached_result'] else None)

    @synchronized
    def save(self, job: Job):
        with self.db:
            self.db.execute('update jobs set idea_id=?,cached_result=? where id=?', (job.idea_id, json.dumps(job.cached_result) if job.cached_result else None, job.id))

    @synchronized
    def complete(self, job_id):
        with self.db:
            self.db.execute("update jobs set state='complete',cached_result=null where id=?", (job_id,))

    @synchronized
    def reschedule(self, job_id, error_code, next_attempt_at):
        with self.db:
            self.db.execute("update jobs set state='pending',retry_count=retry_count+1,error_code=?,next_attempt_at=? where id=?", (error_code, next_attempt_at.timestamp(), job_id))

    @synchronized
    def defer(self, job_id, error_code, next_attempt_at):
        with self.db:
            self.db.execute("update jobs set state='pending',error_code=?,next_attempt_at=? where id=?", (error_code,next_attempt_at.timestamp(),job_id))

    @synchronized
    def fail(self, job_id, error_code):
        with self.db:
            self.db.execute("update jobs set state='failed',error_code=? where id=?", (error_code, job_id))

    @synchronized
    def pending_count(self):
        return self.db.execute("select count(*) from jobs where state in ('pending','processing')").fetchone()[0]
