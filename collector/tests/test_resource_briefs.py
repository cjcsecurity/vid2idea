import json
import pytest
from vid2idea.models import GeneratedBrief, Evidence


def test_resource_brief_preserves_names_links_and_application_kinds():
    result = GeneratedBrief.model_validate({'title': 'Investor Watch', 'brief': {
        'summary': 'A public investor research tool.',
        'resources': [{'name': 'Investor Watch', 'url': 'https://example.com/investors', 'summary': 'Tracks reported portfolios.'}],
        'use_cases': [{'title': 'Enrich an analysis agent', 'description': 'Compare reported portfolios with technical signals.', 'kind': 'project', 'project': 'analysis-agent'}]
    }})
    assert result.brief.resources[0].url == 'https://example.com/investors'
    assert result.brief.use_cases[0].project == 'analysis-agent'


def test_resource_links_cannot_execute_scripts():
    with pytest.raises(ValueError):
        GeneratedBrief.model_validate({'title': 'Tool', 'brief': {'summary': 'A tool.', 'resources': [
            {'name': 'Tool', 'url': 'javascript:alert(1)', 'summary': 'A tool.'}
        ]}})


def test_model_links_and_project_connections_must_be_grounded():
    from vid2idea.resources import finalize_generated
    result = GeneratedBrief.model_validate({'title': 'Tools', 'brief': {'summary': 'Two tools.',
        'resources': [
            {'name': 'Shown tool', 'url': 'https://example.com/tool', 'summary': 'Shown on screen.'},
            {'name': 'Guessed tool', 'url': 'https://invented.example.org', 'summary': 'Its address was unclear.'}],
        'use_cases': [{'title': 'Use in real project', 'description': 'Add a research feed.', 'kind': 'project', 'project': 'research-agent'},
                      {'title': 'Use in imagined project', 'description': 'Add a feed.', 'kind': 'project', 'project': 'made-up-agent'}]}})
    evidence = Evidence(text='Useful tools', ocr_text='https://example.com/tool')
    finalize_generated(result, evidence, [{'name': 'research-agent', 'description': 'Research assistant.'}])
    assert result.brief.resources[0].url == 'https://example.com/tool'
    assert result.brief.resources[1].url is None
    assert result.brief.use_cases[0].kind == 'project'
    assert result.brief.use_cases[1].kind == 'general'
    assert result.brief.use_cases[1].project is None


def test_local_project_context_reads_only_bounded_project_documents(tmp_path):
    from vid2idea.project_context import load_project_context
    from vid2idea.config import Settings
    project = tmp_path / 'projects' / 'analysis-agent'
    project.mkdir(parents=True)
    (project/'README.md').write_text('# Analysis agent\nCombines market research and technical signals.\nAPI_KEY=secret-canary\n')
    (project/'.env').write_text('PRIVATE_TOKEN=env-canary')
    (project/'package.json').write_text(json.dumps({'name': 'analysis-agent', 'description': 'A research assistant.'}))
    (tmp_path/'projects'/'symlink').symlink_to(project, target_is_directory=True)
    context = load_project_context(Settings(project_roots=str(tmp_path/'projects'), data_dir=tmp_path/'cache'))
    assert [item['name'] for item in context] == ['analysis-agent']
    assert 'technical signals' in context[0]['description']
    assert 'canary' not in json.dumps(context)


def test_github_outage_preserves_local_project_context(monkeypatch,tmp_path):
    from vid2idea.project_context import load_project_context
    from vid2idea.config import Settings
    import subprocess
    project=tmp_path/'projects'/'garden-controller';project.mkdir(parents=True)
    (project/'README.md').write_text('# Garden controller\nMonitors irrigation and soil moisture.')
    def unavailable(*args,**kwargs): raise OSError('offline')
    monkeypatch.setattr(subprocess,'run',unavailable)
    result=load_project_context(Settings(project_roots=str(tmp_path/'projects'),github_owner='owner',data_dir=tmp_path/'cache'))
    assert result[0]['name']=='garden-controller'


def test_generation_receives_screen_text_links_and_project_descriptions(tmp_path):
    from vid2idea.ai import build_messages
    from vid2idea.config import Settings
    project=tmp_path/'projects'/'research-agent';project.mkdir(parents=True)
    (project/'README.md').write_text('# Research agent\nCollects and compares investment research.')
    evidence=Evidence(text='A research website',source_url='https://example.org/video',ocr_text='https://example.com/investors')
    messages,_=build_messages(evidence,'My note',Settings(project_roots=str(tmp_path/'projects'),data_dir=tmp_path/'cache'))
    payload=json.loads(messages[1]['content'][0]['text'])
    assert payload['on_screen_text']=='https://example.com/investors'
    assert payload['source_url']=='https://example.org/video'
    assert payload['projects'][0]['name']=='research-agent'
@pytest.mark.parametrize('text',['example.company','example.com.au'])
def test_observed_domains_do_not_truncate_hostname_suffixes(text):
    from vid2idea.resources import observed_urls
    assert 'https://example.com' not in observed_urls(text)
    assert 'https://'+text in observed_urls(text)

@pytest.mark.parametrize('url',['http://127.1','http://127.0.0.01','http://localhost.','http://0x7f.1','http://local%68ost.'])
def test_resource_rejects_browser_normalized_private_hosts(url):
    from vid2idea.models import Resource
    with pytest.raises(ValueError):
        Resource(name='Source',url=url,summary='Source link')

def test_unreadable_optional_project_does_not_hide_other_projects(monkeypatch,tmp_path):
    from pathlib import Path
    from vid2idea.project_context import local_projects
    for name in ['unreadable','available']:
        folder=tmp_path/name;folder.mkdir()
        (folder/'README.md').write_text('A useful project description.')
    original=Path.open
    def read(path,*args,**kwargs):
        if path.parent.name=='unreadable':
            raise PermissionError('Cannot read optional description')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',read)
    assert [item['name'] for item in local_projects(str(tmp_path))] == ['available']
