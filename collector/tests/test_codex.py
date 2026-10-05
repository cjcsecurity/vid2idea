import json
from pathlib import Path
from types import SimpleNamespace
from vid2idea.models import Evidence

def test_codex_uses_schema_images_and_isolates_collector_secrets(monkeypatch,tmp_path):
    from vid2idea.codex import generate_with_codex
    from vid2idea.config import Settings
    import subprocess
    frame = tmp_path/'frame.jpg'
    frame.write_bytes(b'image')
    seen = []
    def run(args, **kwargs):
        if args[1:3] == ['login','status']:
            return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using ChatGPT')
        seen.append((args,kwargs))
        output = Path(args[args.index('--output-last-message')+1])
        output.write_text(json.dumps({'title':'A planter','brief':{'summary':'Build a planter','details':[],'suggested_steps':[],'open_questions':[]},'tags':['garden']}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,'run',run)
    monkeypatch.setenv('SUPABASE_SECRET_KEY','must-not-reach-codex')
    evidence = Evidence(text='A planter',frames=[frame])
    result = generate_with_codex(evidence,'Use cedar',Settings(ai_provider='codex'))
    args,kwargs = seen[0]
    assert result.title == 'A planter'
    assert '--ignore-user-config' in args and '--output-schema' in args
    assert 'web_search="disabled"' in args and '--json' not in args
    assert 'features.code_mode_host=false' in args
    assert args[args.index('--sandbox')+1] == 'read-only'
    assert '-i' in args and str(frame) in args
    assert 'SUPABASE_SECRET_KEY' not in kwargs['env']
    assert 'video_frames' in evidence.kinds

def test_codex_rejects_api_key_authentication(monkeypatch):
    from vid2idea.codex import generate_with_codex
    from vid2idea.config import Settings
    from vid2idea.urls import SourceError
    import subprocess, pytest
    calls=[]
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using an API key')
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises(SourceError,match='codex_subscription_login_required'):
        generate_with_codex(Evidence(text='A planter'),'Try this',Settings())
    assert len(calls)==1


def test_codex_login_and_execution_share_shortened_deadline(monkeypatch):
    from vid2idea.codex import run_codex
    from vid2idea.config import Settings
    from vid2idea.research import ResearchReport
    import subprocess, time
    seen=[]
    ticks=iter([100,105])
    monkeypatch.setattr(time,'monotonic',lambda:next(ticks))
    def run(args,**kwargs):
        seen.append(kwargs['timeout'])
        if args[1:3]==['login','status']:
            return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using ChatGPT')
        Path(args[args.index('--output-last-message')+1]).write_text('{"results":[]}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,'run',run)
    run_codex('Public research',ResearchReport,Settings(),search=True,timeout=12)
    assert seen==[12,7]
