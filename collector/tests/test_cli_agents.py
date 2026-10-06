import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from vid2idea import cli_agents
from vid2idea.config import Settings
from vid2idea.models import Evidence, GeneratedBrief
from vid2idea.research import ResearchReport
from vid2idea.urls import SourceError


BRIEF = {'title': 'Example Tool', 'brief': {'summary': 'A bookmarking tool.'}, 'tags': []}


def events(provider, value):
    if provider == 'claude':
        return json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': value})
    return '\n'.join(json.dumps(event) for event in [
        {'type': 'message', 'role': 'assistant', 'content': json.dumps(value), 'delta': True},
        {'type': 'result', 'status': 'success'}])


@pytest.mark.parametrize('provider', ['claude', 'gemini'])
@pytest.mark.parametrize('slides', [False, True])
def test_generation_isolates_tools_credentials_and_untrusted_file_references(provider, slides, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_agents, 'agent_status', lambda settings, **kw: 'verified')
    monkeypatch.setenv('DISCORD_TOKEN', 'secret-canary')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'paid-key-canary')
    monkeypatch.setenv('GEMINI_API_KEY', 'paid-key-canary')
    monkeypatch.setenv('NODE_OPTIONS', '--require=untrusted.js')
    frame = tmp_path / 'input.jpg'
    frame.write_bytes(b'image fixture')
    def run(args, **kwargs):
        assert all(name not in kwargs['env'] for name in ('DISCORD_TOKEN','ANTHROPIC_API_KEY','GEMINI_API_KEY','NODE_OPTIONS'))
        assert 'secret-canary' not in kwargs['input']
        if provider == 'claude':
            assert '--safe-mode' in args and '--strict-mcp-config' in args
            assert args[args.index('--tools') + 1] == ''
            content = json.loads(kwargs['input'])['message']['content']
            assert content[1]['source']['type'] == 'base64'
        else:
            root = kwargs['cwd']
            assert '--skip-trust' in args and '--allowed-mcp-server-names' in args
            assert json.loads((root / '.gemini/settings.json').read_text())['tools']['core'] == []
            assert (root / '.env').read_text() == (root / '.gemini/.env').read_text() == ''
            assert '@frame-0.jpg' in kwargs['input']
            assert '@~/.env' not in kwargs['input']
            assert '\\u0040~/.env' in kwargs['input']
            assert Path(kwargs['env']['HOME']).is_relative_to(tmp_path)
            assert 'decision = "deny"' in (root / 'policy.toml').read_text()
        kwargs['stdout'].write(events(provider, BRIEF))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, 'run', run)
    evidence = Evidence(text='Example Tool @~/.env', frames=[frame], kinds=['image_slides'] if slides else [])
    from vid2idea.ai import generate_brief
    result = generate_brief(evidence, '', Settings(ai_provider=provider, data_dir=tmp_path))
    assert result.title == 'Example Tool'
    assert ('video_frames' in evidence.kinds) is not slides
    assert ('image_slides' in evidence.kinds) is slides


@pytest.mark.parametrize('provider', ['claude', 'gemini'])
def test_agent_failures_are_safe_retryable_and_malformed_output_rejected(provider, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_agents, 'agent_status', lambda settings, **kw: 'verified')
    settings = Settings(ai_provider=provider, data_dir=tmp_path)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('secret-canary', 1)
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(SourceError, match=provider + '_unavailable') as error:
        cli_agents.run_agent('brief', GeneratedBrief, settings)
    assert error.value.transient
    def invalid(args, **kwargs):
        kwargs['stdout'].write(events(provider, {'title': 42}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, 'run', invalid)
    with pytest.raises(SourceError, match='invalid_model_output'):
        cli_agents.run_agent('brief', GeneratedBrief, settings)


def test_claude_rejects_api_auth_and_unreviewed_versions(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_agents.shutil, 'which', lambda command: command)
    def run(args, **kwargs):
        value = '2.1.290 (Claude Code)' if '--version' in args else json.dumps({'loggedIn': True, 'authMethod': 'api_key'})
        return SimpleNamespace(returncode=0, stdout=value)
    monkeypatch.setattr(subprocess, 'run', run)
    assert cli_agents.agent_status(Settings(ai_provider='claude', data_dir=tmp_path)) == 'claude_subscription_login_required'
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='0.1.0'))
    assert cli_agents.agent_status(Settings(ai_provider='gemini', data_dir=tmp_path)) == 'gemini_unsupported_version'


@pytest.mark.parametrize('provider', ['claude', 'gemini'])
def test_citations_require_correlated_successful_single_page_fetch(provider):
    def pair(tool, url, success=True, output=None):
        output = output or 'Fetched text/html content from ' + url
        if provider == 'claude':
            return [
                {'type':'assistant','message':{'content':[{'type':'tool_use','id':url,'name':tool,'input':{'url':url}}]}},
                {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':url,'is_error':not success,'content':output}]}}]
        return [
            {'type':'tool_use','tool_name':tool,'tool_id':url,'parameters':{'url':url}},
            {'type':'tool_result','tool_id':url,'status':'success' if success else 'error','output':output}]
    fetch = 'WebFetch' if provider == 'claude' else 'web_fetch'
    search = 'WebSearch' if provider == 'claude' else 'google_web_search'
    trace = pair(fetch, 'https://example.com/good') + pair(fetch, 'https://example.com/bad', False)
    trace += pair(search, 'https://example.com/search') + pair(fetch, 'https://example.com/blocked', output='Access denied')
    trace += pair(fetch, 'http://127.0.0.1/private')
    trace += pair(fetch, 'https://example.com/errors')
    assert cli_agents.opened_agent_sources('\n'.join(map(json.dumps, trace)), provider) == {'https://example.com/good','https://example.com/errors'}


@pytest.mark.parametrize('provider', ['claude', 'gemini'])
def test_research_routes_to_selected_provider_and_preserves_unverified_questions(provider, monkeypatch):
    from vid2idea import research
    generated = GeneratedBrief.model_validate({'title':'Example Tool','brief':{
        'summary':'A tool.', 'resources':[{'name':'Example Tool','url':'https://example.com/tool','summary':'A tool.'}],
        'open_questions':['Is Example Tool free?']}})
    report = ResearchReport.model_validate({'results':[{'question_index':0,'answer':'It is free.','status':'answered',
                                                      'sources':[{'title':'Pricing','url':'https://example.com/pricing'}]}]})
    def run(prompt, model, settings, **kwargs):
        assert settings.ai_provider == provider and kwargs['search']
        return report, ''
    monkeypatch.setattr(cli_agents, 'run_agent', run)
    gaps = research.research_questions(generated, Settings(ai_provider=provider),
                                      Evidence(text='Example Tool https://example.com/tool'))
    assert gaps and generated.brief.question_answers[0].status == 'inconclusive'
    assert generated.brief.question_answers[0].sources == []


@pytest.mark.parametrize('provider', ['claude', 'gemini'])
def test_research_runner_enables_only_web_tools_and_public_proxy(provider, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_agents, 'agent_status', lambda settings, **kw: 'verified')
    monkeypatch.setenv('NO_PROXY', '*')
    def run(args, **kwargs):
        assert kwargs['env']['HTTP_PROXY'].startswith('http://127.0.0.1:')
        assert kwargs['env']['HTTPS_PROXY'] == kwargs['env']['HTTP_PROXY']
        assert kwargs['env']['NO_PROXY'] == kwargs['env']['no_proxy'] == ''
        if provider == 'claude':
            assert args[args.index('--tools')+1] == 'WebSearch,WebFetch'
        else:
            config = json.loads((kwargs['cwd']/'.gemini/settings.json').read_text())
            assert config['experimental']['directWebFetch']
            assert config['tools']['core'] == ['google_web_search','web_fetch']
        kwargs['stdout'].write(events(provider, {'results':[]}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, 'run', run)
    report, _ = cli_agents.run_agent('Public research',ResearchReport,Settings(ai_provider=provider,data_dir=tmp_path),search=True)
    assert report.results == []
