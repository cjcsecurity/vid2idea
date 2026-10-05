from datetime import datetime, timedelta, timezone
from vid2idea.models import SourceCapture, GeneratedBrief, Brief, Evidence, RetryRequest
import pytest

pytestmark = pytest.mark.usefixtures('codex_available')

def make_capture():
    return SourceCapture(channel_id='123456789012345678',message_id='223456789012345678',original_url='https://example.com/a',canonical_url='https://example.com/a',shared_at=datetime.now(timezone.utc))

class Cloud:
    def __init__(self):
        self.ids, self.uploads, self.acks = set(), [], []
        self.timeout_ingest = False
        self.timeout_publish = False
    def ingest(self, capture):
        self.ids.add(capture.canonical_url)
        if self.timeout_ingest:
            self.timeout_ingest = False
            raise TimeoutError()
        return 'idea-id'
    def status(self, idea_id, status, code=None): pass
    def is_finished(self, idea_id): return False
    def publish_payload(self, idea_id, payload):
        self.uploads.append(payload)
        if self.timeout_publish:
            self.timeout_publish = False
            raise TimeoutError()
    def acknowledge_retry(self, idea_id, request_id): self.acks.append(request_id)

def result(*args):
    return {'title':'A garden','brief':Brief(summary='A garden with a timer').model_dump(),'tags':['garden'],'evidence_text':'Timer','evidence_kinds':['article_text'],'evidence_gaps':[],'processing_status':'ready','error_code':None}

def test_committed_ingest_timeout_keeps_same_capture(tmp_path):
    from vid2idea.outbox import Outbox
    from vid2idea.worker import Worker
    from vid2idea.config import Settings
    box, cloud = Outbox(tmp_path/'jobs.sqlite'), Cloud()
    box.enqueue([make_capture()],make_capture().channel_id,make_capture().message_id)
    cloud.timeout_ingest = True
    worker = Worker(box, cloud, Settings(ai_base_url='http://localhost:1234/v1',ai_model='local'), processor=result)
    now = datetime.now(timezone.utc)
    assert worker.run_once(now) == 'rescheduled'
    assert box.pending_count() == 1
    assert worker.run_once(now+timedelta(hours=1)) == 'processed'
    assert len(cloud.ids) == 1

def test_publish_timeout_reuses_persisted_result(tmp_path):
    from vid2idea.outbox import Outbox
    from vid2idea.worker import Worker
    from vid2idea.config import Settings
    path = tmp_path/'jobs.sqlite'
    box, cloud, calls = Outbox(path), Cloud(), []
    box.enqueue([make_capture()],make_capture().channel_id,make_capture().message_id)
    def processor(*args):
        calls.append(True)
        payload=result()
        payload['brief']['question_answers']=[{'question':'Is there a guide?','answer':'The official guide is available.','status':'answered','sources':[{'title':'Guide','url':'https://example.com/guide'}],'checked_at':'2026-10-05T12:00:00Z'}]
        return {**payload, 'image_uploads':[{'sha256':'a'*64,'data':'saved image bytes','caption':'Still'}]}
    cloud.timeout_publish = True
    now = datetime.now(timezone.utc)
    assert Worker(box,cloud,Settings(ai_base_url='http://localhost/v1',ai_model='local'),processor=processor).run_once(now) == 'rescheduled'
    box.close()
    box = Outbox(path)
    assert Worker(box,cloud,Settings(),processor=processor).run_once(now+timedelta(hours=1)) == 'processed'
    assert len(calls) == 1
    assert cloud.uploads[0] == cloud.uploads[1]
    assert cloud.uploads[1]['image_uploads'][0]['data'] == 'saved image bytes'
    assert cloud.uploads[1]['brief']['question_answers'][0]['sources'][0]['url']=='https://example.com/guide'

def test_retry_id_is_durable_and_acknowledges_only_its_request(tmp_path):
    from vid2idea.outbox import Outbox
    from vid2idea.worker import Worker
    from vid2idea.config import Settings
    box, cloud = Outbox(tmp_path/'jobs.sqlite'), Cloud()
    request = RetryRequest(id='request-a',idea_id='idea-id',capture=make_capture(),requested_at=datetime.now(timezone.utc))
    box.enqueue_retry(request)
    box.enqueue_retry(request)
    worker = Worker(box,cloud,Settings(ai_base_url='http://localhost/v1',ai_model='local'),processor=result)
    assert worker.run_once() == 'processed'
    assert worker.run_once() == 'idle'
    assert cloud.acks == ['request-a']

def test_missing_ai_keeps_cloud_link_queued(tmp_path):
    from vid2idea.outbox import Outbox
    from vid2idea.worker import Worker
    from vid2idea.config import Settings
    box, cloud = Outbox(tmp_path/'jobs.sqlite'), Cloud()
    box.enqueue([make_capture()],make_capture().channel_id,make_capture().message_id)
    assert Worker(box,cloud,Settings(ai_provider='openai'),processor=result).run_once() == 'rescheduled'
    assert len(cloud.ids) == 1
    assert box.pending_count() == 1

def test_prolonged_cloud_failure_does_not_replace_cached_brief(tmp_path):
    from vid2idea.outbox import Outbox
    from vid2idea.worker import Worker
    from vid2idea.config import Settings
    box, cloud = Outbox(tmp_path/'jobs.sqlite'), Cloud()
    box.enqueue([make_capture()],make_capture().channel_id,make_capture().message_id)
    calls=[]
    def processor(*args): calls.append(True); return result()
    worker=Worker(box,cloud,Settings(),processor=processor)
    now=datetime.now(timezone.utc)
    for i in range(7):
        cloud.timeout_publish=True
        worker.run_once(now+timedelta(hours=i))
    job=box.claim(now+timedelta(hours=8))
    assert job.cached_result['brief']['summary'] == 'A garden with a timer'
    assert len(calls)==1
