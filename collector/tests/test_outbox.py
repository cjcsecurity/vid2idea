from datetime import datetime, timezone
import pytest
from vid2idea.models import SourceCapture

def capture(url='https://example.com/a'):
    return SourceCapture(channel_id='123456789012345678', message_id='223456789012345678', original_url=url, canonical_url=url, shared_at=datetime.now(timezone.utc))

def test_survives_reopen_and_deduplicates(tmp_path):
    from vid2idea.outbox import Outbox
    path = tmp_path / 'outbox.sqlite'
    box = Outbox(path)
    box.enqueue([capture(), capture()], capture().channel_id, capture().message_id)
    box.close()
    box = Outbox(path)
    job = box.claim(datetime.now(timezone.utc))
    assert job.capture.original_url == 'https://example.com/a'
    assert box.claim(datetime.now(timezone.utc)) is None
    box.complete(job.id)
    assert box.pending_count() == 0

def test_failed_transaction_does_not_advance_cursor(tmp_path):
    from vid2idea.outbox import Outbox
    box = Outbox(tmp_path / 'outbox.sqlite')
    box.db.execute("create trigger fail before insert on jobs begin select raise(abort,'test'); end")
    with pytest.raises(Exception):
        box.enqueue([capture()], capture().channel_id, capture().message_id)
    assert box.cursor(capture().channel_id) is None
    assert box.pending_count() == 0

def test_restart_recovers_claim_and_cursor_never_goes_backwards(tmp_path):
    from vid2idea.outbox import Outbox
    path = tmp_path / 'outbox.sqlite'
    box = Outbox(path)
    box.enqueue([capture()], capture().channel_id, '323456789012345678')
    first = box.claim(datetime.now(timezone.utc))
    box.enqueue([], capture().channel_id, '223456789012345678')
    assert box.cursor(capture().channel_id) == '323456789012345678'
    box.close()
    box = Outbox(path)
    assert box.claim(datetime.now(timezone.utc)).id == first.id
