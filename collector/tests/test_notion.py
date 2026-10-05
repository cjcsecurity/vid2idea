import base64
import hashlib
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import httpx
import pytest

from vid2idea.config import Settings
from vid2idea.models import SourceCapture
from vid2idea.outbox import Outbox
from vid2idea.local_library import LocalLibrary
from vid2idea.notion_api import NotionAPI, PublicationError
from vid2idea.notion_content import rich_text, render_article, page_properties


def capture(url='https://example.com/idea', message='1222222222222222221'):
    return SourceCapture(channel_id='1222222222222222220', message_id=message,
                         original_url=url, canonical_url=url, note='Useful idea',
                         shared_at=datetime(2026, 10, 1, tzinfo=timezone.utc))


def settings(**kw):
    return Settings(publishing_backend='notion', notion_api_token='test-only',
                    notion_library_data_source_id=str(uuid4()),
                    notion_projects_data_source_id=str(uuid4()),
                    notion_vid2idea_project_page_id=str(uuid4()), **kw)


def payload():
    return {'title':'Useful project', 'brief':{'summary':'A useful project.',
        'resources':[{'name':'Example', 'url':'https://example.com', 'summary':'What it does.'}],
        'details':['Detail'], 'suggested_steps':['Try it'],
        'use_cases':[{'title':'Connect it','description':'Extend my existing project','kind':'project','project':'Workbench'}],
        'question_answers':[{'question':'Free?','answer':'Unclear','status':'inconclusive',
          'checked_at':'2026-10-05T00:00:00Z','sources':[{'title':'Pricing','url':'https://example.com/pricing'}]}],
        'open_questions':['Which account?']},'tags':['ideas'], 'processing_status':'ready',
        'error_code':None, 'evidence_kinds':['on_screen_text'], 'evidence_gaps':['No pricing shown']}


def test_local_identity_provenance_snapshot_survive_restart(tmp_path):
    path=tmp_path/'outbox.sqlite'
    box=Outbox(path); lib=LocalLibrary(box)
    id=lib.ingest(capture())
    assert lib.ingest(capture(message='1222222222222222222')) == id
    lib.save_payload(id,payload())
    box.close()
    box=Outbox(path); lib=LocalLibrary(box)
    assert lib.ingest(capture()) == id
    assert len(lib.shares(id)) == 2
    assert lib.get(id)['payload']['brief']['resources'][0]['name'] == 'Example'
    assert lib.get(id)['saved_at'] == capture().shared_at.isoformat()
    box.close()


def test_import_preserves_cloud_identity_and_initial_props(tmp_path):
    box=Outbox(tmp_path/'outbox.sqlite'); lib=LocalLibrary(box)
    id=str(uuid4())
    lib.register(id,capture(), {'personal_notes':'x'*20000,'favorite':True,'stage':'trying'})
    assert lib.ingest(capture()) == id
    with pytest.raises(PublicationError, match='identity_conflict'):
        lib.register(str(uuid4()),capture())
    props=page_properties(lib.get(id),payload(),create=True,project_page_id=str(uuid4()))
    assert ''.join(x['text']['content'] for x in props['Personal notes']['rich_text']) == 'x'*20000
    assert props['Stage']['select']['name'] == 'Trying'
    updated=page_properties(lib.get(id),payload(),create=False)
    assert not set(updated) & {'Kind','Saved at','Projects','Stage','Favorite','Personal notes','Review status','Refresh article'}
    box.close()


def test_renderer_preserves_links_research_images_and_legacy_failures():
    article=render_article(payload(),[capture().model_dump(mode='json')],[])
    text=json.dumps(article)
    assert 'https://example.com/pricing' in text and '2026-10-05' in text
    assert 'Workbench' in text and 'No pricing shown' in text and 'Useful idea' in text
    p=payload(); p['image_uploads']=[{'caption':'Screenshot','timestamp_seconds':12}]
    assert any(b['type']=='image' for b in render_article(p,[],['upload-id']))
    assert 'unsupported_source' in json.dumps(render_article({'processing_status':'blocked','error_code':'unsupported_source'},[capture().model_dump(mode='json')],[]))
    assert all(len(x['text']['content'])<=2000 for x in rich_text('x'*20000))


@pytest.mark.parametrize('status,code',[(401,'notion_authentication'),(403,'notion_access'),(429,'notion_rate_limited'),(529,'notion_unavailable')])
def test_http_errors_are_safe_and_retry_after_honored(status,code):
    def handler(req):
        assert req.headers['notion-version'] == '2026-03-11'
        return httpx.Response(status,headers={'Retry-After':'73'},json={'message':'do-not-log-secret','code':'rate_limited'})
    api=NotionAPI(settings(),transport=httpx.MockTransport(handler),interval=0)
    with pytest.raises(PublicationError) as exc:
        api.request('GET','/users/me')
    assert exc.value.code == code
    assert 'do-not-log-secret' not in str(exc.value)
    assert exc.value.retry_after == 73


def test_committed_write_metadata_is_preserved_without_replay():
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(503,json={'additional_data':{'committed_resource_id':'parent','committed_child_ids':['child']}})
    api=NotionAPI(settings(),transport=httpx.MockTransport(handler),interval=0)
    with pytest.raises(PublicationError) as exc:
        api.request('PATCH','/blocks/parent/children',json={'children':[]})
    assert exc.value.uncertain and exc.value.committed_ids == ['child']
    assert exc.value.committed_resource_id == 'parent' and len(calls)==1


def test_notion_configuration_has_no_supabase_dependency():
    s=settings()
    assert s.missing(discord=False) == []
    s.notion_api_token=''
    assert 'NOTION_API_TOKEN' in s.missing(discord=False)


def test_pipeline_strips_collector_secrets_from_media_environment(monkeypatch,tmp_path):
    from vid2idea import pipeline
    secrets = ('DISCORD_TOKEN','SUPABASE_SECRET_KEY','NOTION_API_TOKEN','GH_TOKEN','AWS_SECRET_ACCESS_KEY','UNRELATED_CREDENTIAL')
    for key in secrets:
        monkeypatch.setenv(key,'secret-canary')
    observed={}
    class Child:
        def communicate(self,input,timeout):
            observed['input']=json.loads(input)
            return json.dumps({'result':payload()}),None
    def popen(*args,**kwargs): observed.update(kwargs); return Child()
    monkeypatch.setattr(pipeline.subprocess,'Popen',popen)
    pipeline.process_capture(capture(),settings(data_dir=tmp_path))
    exposed=set(observed['env']) & set(secrets)
    assert exposed==set()
    assert observed['input']['settings']['notion_api_token']==''
