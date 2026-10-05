import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from vid2idea.models import Brief, GeneratedBrief, Evidence
from vid2idea.config import Settings


def brief():
    return GeneratedBrief(title='Research tool',brief=Brief(summary='A tool for research.',resources=[{'name':'Public Tool','url':'https://example.com/tool','summary':'A research tool.'}],open_questions=['Does it require payment?','Which countries qualify?']))


def public_evidence():
    return Evidence(text='Public Tool https://example.com/tool https://example.com/apply')


def test_answer_contract_preserves_sources_and_checked_date():
    data={'summary':'A tool','question_answers':[{'question':'Does it require payment?','answer':'A free plan is documented.','status':'answered','sources':[{'title':'Pricing','url':'https://example.com/pricing'}],'checked_at':'2026-10-05T12:00:00Z'}]}
    result=Brief.model_validate(data)
    assert result.question_answers[0].sources[0].url=='https://example.com/pricing'
    assert result.question_answers[0].checked_at.tzinfo is not None


def test_research_citations_require_successfully_opened_pages():
    from vid2idea.research import finalize_research
    generated=brief()
    report={'results':[{'question_index':0,'answer':'A free plan is documented.','status':'answered','sources':[{'title':'Pricing','url':'https://example.com/pricing'},{'title':'Invented','url':'https://invented.example.org'}]}]}
    now=datetime(2026,10,5,tzinfo=timezone.utc)
    finalize_research(generated,report,{'https://example.com/pricing'},now)
    answer=generated.brief.question_answers[0]
    assert [source.url for source in answer.sources]==['https://example.com/pricing']
    assert answer.status=='answered' and answer.checked_at==now
    assert generated.brief.question_answers[1].status=='inconclusive'
    assert generated.brief.open_questions==['Does it require payment?','Which countries qualify?']


def test_uncited_or_duplicate_index_answers_cannot_claim_resolution():
    from vid2idea.research import finalize_research
    generated=brief()
    report={'results':[{'question_index':0,'answer':'Certainly free.','status':'answered','sources':[]},{'question_index':0,'answer':'Actually paid','status':'answered','sources':[]},{'question_index':99,'answer':'Invented question','status':'answered','sources':[]}]}
    finalize_research(generated,report,set(),datetime.now(timezone.utc))
    assert len(generated.brief.question_answers)==2
    assert all(answer.status=='inconclusive' for answer in generated.brief.question_answers)
    assert all('Certainly free' not in answer.answer for answer in generated.brief.question_answers)


def test_research_payload_excludes_private_project_questions_and_personal_context(tmp_path):
    from vid2idea.research import research_payload
    root=tmp_path/'projects'/'private-agent';root.mkdir(parents=True)
    (root/'README.md').write_text('A private project description canary.')
    generated=brief()
    generated.brief.open_questions+=['How can private-agent use this?','Does my location qualify?','Contact owner@example.org?']
    settings=Settings(project_roots=str(tmp_path/'projects'),brief_context='private context canary',data_dir=tmp_path/'data')
    from vid2idea.project_context import load_project_context
    load_project_context(settings)
    payload,blocked=research_payload(generated,settings,public_evidence())
    text=json.dumps(payload)
    assert 'private-agent' not in text and 'canary' not in text and 'owner@example.org' not in text
    assert [item['question_index'] for item in payload['questions']]==[0,1]
    assert set(blocked)=={2,3,4}


def test_subscription_research_failure_keeps_brief_and_marks_questions(monkeypatch):
    from vid2idea import research
    from vid2idea.urls import SourceError
    generated=brief()
    def unavailable(*args,**kwargs):raise SourceError('codex_unavailable',transient=True)
    monkeypatch.setattr(research,'run_codex',unavailable)
    gaps=research.research_questions(generated,Settings(),public_evidence())
    assert generated.brief.summary=='A tool for research.'
    assert len(generated.brief.question_answers)==2
    assert all(answer.status=='inconclusive' for answer in generated.brief.question_answers)
    assert 'could not' in gaps[0]


def test_research_input_omits_generated_descriptions_and_url_tracking(tmp_path):
    from vid2idea.research import research_payload
    generated=brief()
    generated.brief.resources[0].summary='A tool for your private description canary.'
    generated.brief.resources[0].url='https://example.com/tool?token=private-canary#tracking'
    payload,_=research_payload(generated,Settings(data_dir=tmp_path),public_evidence())
    assert payload['resources']==[{'name':'Public Tool','url':'https://example.com/tool'}]


def test_generated_resource_cannot_exempt_private_project_name(tmp_path):
    from vid2idea.research import research_payload
    root=tmp_path/'projects'/'private-agent';root.mkdir(parents=True)
    (root/'README.md').write_text('Private context.')
    generated=brief()
    generated.brief.resources[0].name='private-agent'
    generated.brief.open_questions=['Can private-agent use the service?']
    settings=Settings(project_roots=str(tmp_path/'projects'),data_dir=tmp_path/'data')
    from vid2idea.project_context import load_project_context
    load_project_context(settings)
    payload,blocked=research_payload(generated,settings,Evidence(text='private-agent https://example.com/tool'))
    assert 'private-agent' not in json.dumps(payload)
    assert 0 in blocked


def test_question_tracking_and_person_identity_cannot_enter_search(tmp_path):
    from vid2idea.research import research_payload
    generated=brief()
    generated.brief.open_questions=['What is available at https://example.com/apply?invite=PRIVATE_CANARY#tracking?', 'Does Jane Doe at 123 Main Street qualify?']
    payload,blocked=research_payload(generated,Settings(data_dir=tmp_path),public_evidence())
    assert 'PRIVATE_CANARY' not in json.dumps(payload)
    assert 'Jane Doe' not in json.dumps(payload)
    assert 1 in blocked
    assert payload['questions']==[{'question_index':0,'question':'What is available at https://example.com/apply'}]


def test_research_resource_requires_public_evidence(tmp_path):
    from vid2idea.research import research_payload
    from vid2idea.models import Evidence
    generated=brief()
    generated.brief.resources[0].name='Unobserved private name'
    payload,_=research_payload(generated,Settings(data_dir=tmp_path),Evidence(text='Public Tool https://example.com/tool'))
    assert 'Unobserved private name' not in json.dumps(payload)


def test_context_failure_cannot_discard_finished_brief(monkeypatch):
    from vid2idea import research
    generated=brief()
    def unavailable(*args,**kwargs):raise OSError('Context unavailable')
    monkeypatch.setattr(research,'load_project_context',unavailable)
    gaps=research.research_questions(generated,Settings(project_roots='/unavailable'),public_evidence())
    assert gaps and generated.brief.summary=='A tool for research.'
    assert all(answer.status=='inconclusive' for answer in generated.brief.question_answers)


def test_research_cannot_refresh_slow_project_catalog(monkeypatch,tmp_path):
    from vid2idea import research,project_context
    calls=[]
    def network(*args):calls.append(True);return []
    monkeypatch.setattr(project_context,'github_projects',network)
    def unavailable(*args,**kwargs):raise OSError('No model call needed')
    monkeypatch.setattr(research,'run_codex',unavailable)
    generated=brief()
    gaps=research.research_questions(generated,Settings(github_owner='owner',data_dir=tmp_path),public_evidence())
    assert not calls
    assert gaps and generated.brief.summary=='A tool for research.'


def test_no_questions_skip_research_call(monkeypatch):
    from vid2idea import research
    generated=GeneratedBrief(title='Complete',brief=Brief(summary='Already complete.'))
    def forbidden(*args,**kwargs):raise AssertionError('Unexpected subscription call')
    monkeypatch.setattr(research,'run_codex',forbidden)
    assert research.research_questions(generated,Settings())==[]


def test_no_opened_sources_marks_research_partial(monkeypatch):
    from vid2idea import research
    generated=brief()
    report=research.ResearchReport.model_validate({'results':[{'question_index':0,'answer':'It is probably free','status':'inconclusive','sources':[]}]})
    monkeypatch.setattr(research,'run_codex',lambda *args,**kwargs:(report,''))
    gaps=research.research_questions(generated,Settings(),public_evidence())
    assert gaps and 'could not' in gaps[0]
    assert 'probably free' not in generated.brief.question_answers[0].answer


def test_opened_page_with_no_results_marks_research_incomplete(monkeypatch):
    from vid2idea import research
    generated=brief()
    trace=json.dumps({'type':'item.completed','item':{'type':'web_search','action':{'type':'open_page'},'results':[{'type':'text_result','title':'Pricing','url':'https://example.com/pricing'}]}})
    monkeypatch.setattr(research,'run_codex',lambda *args,**kwargs:(research.ResearchReport(results=[]),trace))
    gaps=research.research_questions(generated,Settings(),public_evidence())
    assert gaps and 'could not' in gaps[0]
    assert all(answer.status=='inconclusive' for answer in generated.brief.question_answers)


def test_search_results_and_failed_opens_do_not_authorize_citations():
    from vid2idea.research import opened_sources
    def event(action,title,url):
        return json.dumps({'type':'item.completed','item':{'type':'web_search','action':{'type':action,'url':url},'results':[{'type':'text_result','title':title,'url':url,'snippet':'Total lines: 30'}]}})
    trace='\n'.join([event('search','Search result','https://example.com/search'),event('open_page','Internal Error','https://example.com/fail'),event('open_page','Pricing','https://example.com/pricing')])
    assert opened_sources(trace)=={'https://example.com/pricing'}


def test_pipeline_automatically_adds_research_before_publication(monkeypatch,tmp_path,capsys):
    from io import StringIO
    from vid2idea import pipeline,research
    from vid2idea.models import Evidence
    generated=brief()
    monkeypatch.setattr(pipeline,'read_article',lambda *args:Evidence(text='Public Tool https://example.com/tool',kinds=['article_text']))
    monkeypatch.setattr(pipeline,'generate_brief',lambda *args:generated)
    report=research.ResearchReport.model_validate({'results':[{'question_index':0,'answer':'A free plan is documented.','status':'answered','sources':[{'title':'Pricing','url':'https://example.com/pricing'}]}]})
    trace=json.dumps({'type':'item.completed','item':{'type':'web_search','action':{'type':'open_page','url':'https://example.com/pricing'},'results':[{'type':'text_result','title':'Pricing','url':'https://example.com/pricing','snippet':'Total lines: 30'}]}})
    monkeypatch.setattr(research,'run_codex',lambda *args,**kwargs:(report,trace))
    request={'capture':{'channel_id':'123456789012345678','message_id':'223456789012345678','original_url':'https://example.com/article','canonical_url':'https://example.com/article','shared_at':'2026-10-05T12:00:00Z'},'settings':{'data_dir':str(tmp_path)},'workdir':str(tmp_path)}
    monkeypatch.setattr(pipeline.sys,'stdin',StringIO(json.dumps(request)))
    pipeline.main()
    result=json.loads(capsys.readouterr().out)['result']
    assert result['brief']['question_answers'][0]['status']=='answered'
    assert result['brief']['question_answers'][0]['sources'][0]['url']=='https://example.com/pricing'
    assert result['brief']['question_answers'][0]['checked_at']
    assert result['brief']['summary']=='A tool for research.'


def test_nearly_expired_pipeline_skips_research_and_keeps_completed_brief(monkeypatch,tmp_path,capsys):
    from io import StringIO
    from vid2idea import pipeline,research
    from vid2idea.models import Evidence
    import time
    calls=[]
    monkeypatch.setattr(time,'monotonic',lambda:1000)
    monkeypatch.setattr(pipeline,'read_article',lambda *args:Evidence(text='Public Tool https://example.com/tool',kinds=['article_text']))
    monkeypatch.setattr(pipeline,'generate_brief',lambda *args:brief())
    def forbidden(*args,**kwargs):calls.append(True);raise AssertionError('Deadline exhausted')
    monkeypatch.setattr(research,'run_codex',forbidden)
    request={'capture':{'channel_id':'123456789012345678','message_id':'223456789012345678','original_url':'https://example.com/article','canonical_url':'https://example.com/article','shared_at':'2026-10-05T12:00:00Z'},'settings':{'data_dir':str(tmp_path)},'workdir':str(tmp_path),'deadline':1008}
    monkeypatch.setattr(pipeline.sys,'stdin',StringIO(json.dumps(request)))
    pipeline.main()
    result=json.loads(capsys.readouterr().out)['result']
    assert not calls
    assert result['brief']['summary']=='A tool for research.'
    assert result['processing_status']=='partial'
    assert all(a['status']=='inconclusive' for a in result['brief']['question_answers'])
    assert 'time' in result['evidence_gaps'][0].lower()


def test_codex_research_only_inherits_allowed_environment_and_enables_live_search(monkeypatch, codex_available):
    from vid2idea.codex import run_codex
    from vid2idea.research import ResearchReport
    import subprocess
    seen=[]
    def run(args,**kwargs):
        if args[1:3]==['login','status']:
            return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using ChatGPT')
        seen.append((args,kwargs))
        Path(args[args.index('--output-last-message')+1]).write_text('{"results":[]}')
        trace='{"type":"item.completed","item":{"type":"web_search","action":{"type":"open_page","url":"https://example.com/pricing"},"results":[{"type":"text_result","title":"Pricing","url":"https://example.com/pricing","snippet":"Total lines: 25"}]}}\n'
        kwargs['stdout'].write(trace)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,'run',run)
    monkeypatch.setenv('SUPABASE_SECRET_KEY','secret-canary')
    _,trace=run_codex('Research public questions',ResearchReport,Settings(),search=True)
    args,options=seen[0]
    assert 'web_search="live"' in args and '--json' in args
    assert 'features.shell_tool=false' in args and 'features.apps=false' in args
    assert 'SUPABASE_SECRET_KEY' not in options['env']
    assert 'secret-canary' not in options['input']
    assert 'https://example.com/pricing' in trace
