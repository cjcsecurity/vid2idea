import pytest
import base64
import hashlib
from types import SimpleNamespace
from vid2idea.models import Brief, GeneratedBrief, Evidence

def test_publication_never_includes_personal_fields():
    from vid2idea.cloud import publication_payload
    payload = publication_payload(GeneratedBrief(title='Timer',brief=Brief(summary='A timer')),Evidence(text='Evidence',kinds=['article_text']), 'ready')
    assert set(payload) == {'title','brief','tags','evidence_kinds','evidence_text','evidence_gaps','processing_status','error_code'}
    assert not set(payload) & {'personal_notes','favorite','stage'}

def test_secret_adapter_rejects_unknown_publication_fields():
    from vid2idea.cloud import validate_publication
    with pytest.raises(ValueError):
        validate_publication({'personal_notes':'overwrite'})

def storage_adapter():
    from vid2idea.cloud import CloudStore
    events = []
    class Bucket:
        def upload(self, path, data, options):
            events.append(('upload', path, data, options))
        def list(self, prefix, options):
            return [{'name':'obsolete.jpg'}]
        def remove(self, paths):
            events.append(('remove', paths))
    def rpc(name, params):
        events.append(('rpc', params))
        return SimpleNamespace(execute=lambda: None)
    cloud = CloudStore.__new__(CloudStore)
    cloud.owner_id = '00000000-0000-4000-8000-000000000001'
    cloud.client = SimpleNamespace(storage=SimpleNamespace(from_=lambda bucket: Bucket()), rpc=rpc)
    return cloud, events

def test_private_images_upload_before_publication_and_cache_is_unchanged():
    cloud, events = storage_adapter()
    idea = '00000000-0000-4000-8000-000000000002'
    data = b'\xff\xd8\xfftest-jpeg'
    digest = hashlib.sha256(data).hexdigest()
    payload = {'title':'Resource', 'image_uploads':[{'sha256':digest,'data':base64.b64encode(data).decode(),'caption':'Source still','timestamp_seconds':8.0}]}
    cloud.publish_payload(idea, payload)
    assert [event[0] for event in events] == ['upload','rpc','remove']
    assert events[0][1] == f'{cloud.owner_id}/{idea}/{digest}.jpg'
    published = events[1][1]['p_generated']
    assert published['images'][0]['caption'] == 'Source still'
    assert 'image_uploads' not in published
    assert payload['image_uploads'][0]['data'] == base64.b64encode(data).decode()
    cloud.publish_payload(idea, payload)
    assert events[3][1] == events[0][1]  # Retry uses the same immutable path.

def test_invalid_image_hash_never_uploads_or_publishes():
    cloud, events = storage_adapter()
    with pytest.raises(ValueError):
        cloud.publish_payload('00000000-0000-4000-8000-000000000002', {'image_uploads':[{'sha256':'bad','data':'AAAA'}]})
    assert events == []

def test_status_publication_preserves_images_without_storage_requests():
    cloud, events = storage_adapter()
    cloud.publish_payload('00000000-0000-4000-8000-000000000002', {'processing_status':'processing'})
    assert [event[0] for event in events] == ['rpc']
    assert 'images' not in events[0][1]['p_generated']
