import os
import json
import stat
from uuid import uuid4

import httpx
import pytest

from vid2idea.config import Settings


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def private_env(path, text):
    path.write_text(text)
    path.chmod(0o600)
    return path


def test_local_env_loads_without_interpolation_or_environment_mutation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CANARY_SECRET', 'must-stay-private')
    private_env(tmp_path / '.env', 'DISCORD_TOKEN=local-token\nBRIEF_CONTEXT=${CANARY_SECRET}\n')
    settings = Settings.from_env()
    assert settings.discord_token.get_secret_value() == 'local-token'
    assert settings.brief_context == '${CANARY_SECRET}'
    assert 'DISCORD_TOKEN' not in os.environ


def test_explicit_env_path_anchors_data_and_environment_takes_precedence(tmp_path, monkeypatch):
    path = private_env(tmp_path / 'config.env', 'AI_MODEL=file-model\nDATA_DIR=data\n')
    monkeypatch.setenv('AI_MODEL', 'environment-model')
    settings = Settings.from_env(path)
    assert settings.ai_model == 'environment-model'
    assert settings.data_dir == tmp_path / 'data'


def test_missing_explicit_env_and_insecure_files_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        Settings.from_env(tmp_path / 'absent.env')
    path = private_env(tmp_path / 'config.env', 'DISCORD_TOKEN=private\n')
    path.chmod(0o644)
    with pytest.raises(ValueError):
        Settings.from_env(path)
    link = tmp_path / 'link.env'
    link.symlink_to(path)
    with pytest.raises(ValueError):
        Settings.from_env(link)


def test_init_creates_private_template_and_never_overwrites(tmp_path, capsys):
    from vid2idea.cli import main
    path = tmp_path / '.env'
    assert main(['init', '--env-file', str(path)]) == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert 'DISCORD_TOKEN=\n' in path.read_text()
    private_env(path, 'DISCORD_TOKEN=secret-canary\n')
    assert main(['init', '--env-file', str(path)]) == 1
    assert path.read_text() == 'DISCORD_TOKEN=secret-canary\n'
    assert 'secret-canary' not in str(capsys.readouterr())


def test_doctor_reports_subscription_authentication_failure(monkeypatch, capsys):
    from types import SimpleNamespace
    from vid2idea.cli import doctor
    monkeypatch.setattr('subprocess.run', lambda *args, **kw: SimpleNamespace(
        returncode=0, stdout='', stderr='Logged in using an API key'))
    assert doctor(Settings()) == 1
    assert 'codex_subscription_login_required' in capsys.readouterr().out


def test_doctor_emits_one_json_document(monkeypatch, capsys):
    from types import SimpleNamespace
    from vid2idea.cli import doctor
    monkeypatch.setattr('subprocess.run', lambda *args, **kw: SimpleNamespace(
        returncode=1, stdout='', stderr='untrusted-token-canary'))
    doctor(Settings())
    report = json.loads(capsys.readouterr().out)
    assert report['next_steps']
    assert 'untrusted-token-canary' not in json.dumps(report)


def test_source_discovery_needs_only_token_and_follows_pagination(monkeypatch):
    from vid2idea.setup import discover_sources
    calls = []
    def handler(req):
        calls.append(req)
        body = json.loads(req.content)
        assert body['filter'] == {'property': 'object', 'value': 'data_source'}
        if len(calls) == 1:
            return httpx.Response(200, json={'results': [{'id': str(uuid4()), 'title': [{'plain_text': 'Library'}]}], 'has_more': True, 'next_cursor': 'second'})
        assert body['start_cursor'] == 'second'
        return httpx.Response(200, json={'results': [], 'has_more': False})
    sources = discover_sources(Settings(notion_api_token='test-only'), transport=httpx.MockTransport(handler))
    assert sources[0]['name'] == 'Library'
    assert len(calls) == 2


def test_notion_project_must_be_active_and_in_configured_source():
    from vid2idea.notion_api import NotionAPI, PublicationError
    source, project = str(uuid4()), str(uuid4())
    settings = Settings(notion_library_data_source_id=str(uuid4()),
                        notion_projects_data_source_id=source,
                        notion_vid2idea_project_page_id=project)
    data = {'parent': {'type': 'data_source_id', 'data_source_id': str(uuid4())}}
    api = NotionAPI(settings, transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data)), interval=0)
    with pytest.raises(PublicationError, match='notion_project_mismatch'):
        api.validate_project(project)
    data['parent']['data_source_id'] = source
    data['in_trash'] = True
    with pytest.raises(PublicationError, match='notion_project_unavailable'):
        api.validate_project(project)
    data['in_trash'] = False
    api.validate_project(project)
    api.close()
