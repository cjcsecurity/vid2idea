"""Restricted Claude Code and Gemini CLI calls; no collector credentials inherited."""
import base64
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext

from .environment import runtime_environment
from .models import EvidenceKind, GeneratedBrief, ResearchSource
from .urls import SourceError
from .safe_proxy import SafeProxy

VERSIONS = {'claude': '2.1.290', 'gemini': '0.62.0'}


def agent_environment(settings):
    environment = runtime_environment()
    if settings.ai_provider == 'gemini':
        # A separate login avoids loading the user's coding-agent customizations.
        home = settings.data_dir.resolve() / 'gemini-home'
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        environment.update(HOME=str(home), GEMINI_CLI_HOME=str(home),
                           GEMINI_CLI_NO_RELAUNCH='1', NO_BROWSER='true')
        for name in ('CODEX_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME'):
            environment.pop(name, None)
    else:
        environment['CLAUDE_CODE_SAFE_MODE'] = '1'
        environment['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
        environment['DISABLE_AUTOUPDATER'] = '1'
    return environment


def agent_status(settings, timeout=30):
    deadline = time.monotonic() + timeout
    provider = settings.ai_provider
    command = getattr(settings, provider + '_command')
    if not shutil.which(command):
        return provider + '_not_installed'
    try:
        with TemporaryDirectory(prefix='vid2idea-agent-check-') as directory:
            root = Path(directory)
            if provider == 'gemini':
                gemini_workspace(root)
            environment = agent_environment(settings)
            version = subprocess.run([command, '--version'], capture_output=True, text=True,
                                     timeout=min(15, timeout), env=environment, cwd=root)
            if version.returncode or not re.search(r'(?<![\d.])' + re.escape(VERSIONS[provider]) + r'(?![\d.])', version.stdout):
                return provider + '_unsupported_version'
            if provider == 'claude':
                result = subprocess.run([command, 'auth', 'status'], capture_output=True,
                                        text=True, timeout=max(0.01, min(15, deadline-time.monotonic())), env=environment, cwd=root)
                auth = json.loads(result.stdout)
                if result.returncode or auth.get('authMethod') != 'claude.ai' or not auth.get('loggedIn'):
                    return 'claude_subscription_login_required'
                return 'verified'
            # File presence is not proof of valid auth or available quota.
            if not (Path(environment['GEMINI_CLI_HOME']) / '.gemini/oauth_creds.json').is_file():
                return 'gemini_login_required'
            return 'login_unverified'
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return provider + '_unavailable'


def gemini_workspace(root, *, search=False):
    config = root / '.gemini'
    config.mkdir()
    # Gemini walks ancestors for dotenv files, even outside its custom HOME.
    # Stop both trusted and untrusted lookup paths at our empty workspace.
    (root / '.env').touch(mode=0o600)
    (config / '.env').touch(mode=0o600)
    settings = {
        'security': {'auth': {'selectedType': 'oauth-personal', 'enforcedType': 'oauth-personal'}},
        'tools': {'core': ['google_web_search', 'web_fetch'] if search else [],
                  'discoveryCommand': '', 'callCommand': ''},
        'hooksConfig': {'enabled': False}, 'skills': {'enabled': False},
        'mcp': {'serverCommand': ''},
        'context': {'fileName': 'VID2IDEA-NO-CONTEXT.md', 'discoveryMaxDirs': 0},
        'general': {'disableAutoUpdate': True},
        'telemetry': {'enabled': False}, 'privacy': {'usageStatisticsEnabled': False},
        'model': {'maxSessionTurns': 20},
        'experimental': {'directWebFetch': True, 'enableAgents': False},
    }
    (config / 'settings.json').write_text(json.dumps(settings))
    policy = root / 'policy.toml'
    policy.write_text('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 900\n' +
                      ('\n[[rule]]\ntoolName = ["google_web_search", "web_fetch"]\ndecision = "allow"\npriority = 999\n' if search else ''))
    return policy


def login_agent(settings):
    provider = settings.ai_provider
    if provider == 'openai':
        raise SourceError('api_provider_uses_env_configuration')
    command = getattr(settings, provider + '_command')
    with TemporaryDirectory(prefix='vid2idea-login-') as directory:
        root = Path(directory)
        environment = runtime_environment() if provider == 'codex' else agent_environment(settings)
        args = [command, 'login'] if provider == 'codex' else [command, 'auth', 'login']
        if provider == 'gemini':
            policy = gemini_workspace(root)
            args = [command, '--skip-trust', '--extensions', 'none', '--policy', str(policy),
                    '--allowed-mcp-server-names', 'vid2idea-disabled-' + root.name]
            print('Choose Sign in with Google, then /quit. This login is isolated to this collector.', flush=True)
        try:
            return subprocess.run(args, cwd=root, env=environment).returncode
        except OSError:
            raise SourceError(provider + '_not_installed') from None


def parse_events(trace, provider, output_model):
    events = [json.loads(line) for line in trace.splitlines() if line.strip()]
    if provider == 'claude':
        results = [event for event in events if event.get('type') == 'result']
        if len(results) != 1 or results[0].get('is_error') or results[0].get('subtype') != 'success':
            raise ValueError('Agent did not complete')
        return output_model.model_validate(results[0]['structured_output'])
    result = [event for event in events if event.get('type') == 'result']
    if len(result) != 1 or result[0].get('status') != 'success':
        raise ValueError('Agent did not complete')
    parts = []
    for event in events:
        if event.get('type') == 'tool_use':
            parts = []
        elif event.get('type') == 'message' and event.get('role') == 'assistant':
            parts.append(event.get('content', ''))
    response = ''.join(parts).strip()
    if response.startswith('```json\n') and response.endswith('\n```'):
        response = response[8:-4]
    return output_model.model_validate_json(response)


def run_agent(prompt, output_model, settings, *, frames=(), search=False, timeout=240):
    provider = settings.ai_provider
    deadline = time.monotonic() + timeout
    status = agent_status(settings, timeout=min(30, timeout))
    if status not in ('verified', 'login_unverified'):
        raise SourceError(status, transient=True, retry_after=300)
    command = getattr(settings, provider + '_command')
    with TemporaryDirectory(prefix='vid2idea-agent-') as directory:
        root = Path(directory)
        environment = agent_environment(settings)
        if provider == 'claude':
            args = [command, '-p', '--safe-mode', '--setting-sources', '',
                    '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                    '--no-session-persistence', '--disable-slash-commands', '--no-chrome',
                    '--permission-mode', 'dontAsk', '--tools', 'WebSearch,WebFetch' if search else '',
                    '--output-format', 'stream-json', '--verbose', '--input-format', 'stream-json',
                    '--json-schema', json.dumps(output_model.model_json_schema()), '--max-turns', '20']
            if search:
                args += ['--allowedTools', 'WebSearch,WebFetch']
            content = [{'type': 'text', 'text': prompt}]
            for frame in frames:
                content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                'data': base64.b64encode(frame.read_bytes()).decode()}})
            payload = json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content}}) + '\n'
        else:
            policy = gemini_workspace(root, search=search)
            args = [command, '--skip-trust', '--extensions', 'none', '--policy', str(policy),
                    '--allowed-mcp-server-names', 'vid2idea-disabled-' + root.name,
                    '--output-format', 'stream-json', '--prompt', 'Return only the requested JSON.']
            # Gemini expands @file references before inference. Only our copied frames
            # may use that syntax, never untrusted evidence or personal context.
            payload = (prompt + '\nJSON schema:\n' + json.dumps(output_model.model_json_schema())).replace('@', '\\u0040')
            for index, frame in enumerate(frames):
                filename = f'frame-{index}.jpg'
                shutil.copyfile(frame, root / filename)
                payload += '\n@' + filename
        model = getattr(settings, provider + '_model')
        if model:
            args += ['--model', model]
        trace_path = root / 'events.jsonl'
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            with SafeProxy(seconds=remaining) if search else nullcontext() as proxy:
                if proxy:
                    environment.update(HTTPS_PROXY=proxy.url, HTTP_PROXY=proxy.url, NO_PROXY='', no_proxy='')
                with trace_path.open('w') as output:
                    result = subprocess.run(args, input=payload, text=True, cwd=root, env=environment,
                                            stdout=output, stderr=subprocess.DEVNULL, timeout=remaining)
            if result.returncode:
                raise SourceError(provider + '_unavailable', transient=True)
            if trace_path.stat().st_size > 4 * 1024 * 1024:
                raise SourceError('invalid_model_output')
            trace = trace_path.read_text()
            return parse_events(trace, provider, output_model), trace
        except (OSError, subprocess.TimeoutExpired):
            raise SourceError(provider + '_unavailable', transient=True) from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise SourceError('invalid_model_output') from None


def generate_with_agent(evidence, note, settings):
    from .ai import SYSTEM, evidence_payload
    from .project_context import load_project_context
    from .resources import finalize_generated
    if not evidence.text.strip() and not evidence.frames:
        raise SourceError('no_readable_evidence')
    projects = load_project_context(settings)
    result, _ = run_agent(SYSTEM + '\n' + json.dumps(evidence_payload(evidence, note, settings, projects)),
                          GeneratedBrief, settings, frames=evidence.frames)
    if evidence.frames:
        evidence.kinds.append(EvidenceKind.video_frames)
    return finalize_generated(result, evidence, projects)


def opened_agent_sources(trace, provider):
    """Only a successful, correlated single-page fetch can authorize a citation."""
    calls, opened = {}, set()
    for line in trace.splitlines():
        try:
            event = json.loads(line)
            if provider == 'claude':
                blocks = event.get('message', {}).get('content', [])
                if not isinstance(blocks, list):
                    continue
                for block in blocks:
                    if event.get('type') == 'assistant' and block.get('type') == 'tool_use' and block.get('name') == 'WebFetch':
                        calls[block['id']] = block.get('input', {}).get('url')
                    if event.get('type') == 'user' and block.get('type') == 'tool_result' and not block.get('is_error'):
                        url = calls.pop(block.get('tool_use_id'), None)
                        content = block.get('content')
                        text = content if isinstance(content,str) else '\n'.join(part.get('text','') for part in content or [] if isinstance(part,dict))
                        if url and text and not re.match(r'(?i)\s*(error:|failed to fetch|access denied|request failed|redirect)', text):
                            ResearchSource(title='Opened source', url=url)
                            opened.add(url)
            else:
                if event.get('type') == 'tool_use' and event.get('tool_name') == 'web_fetch':
                    # Batch prompt results don't prove which individual URLs worked.
                    calls[event['tool_id']] = event.get('parameters', {}).get('url')
                if event.get('type') == 'tool_result':
                    url = calls.pop(event.get('tool_id'), None)
                    output = event.get('output', '')
                    fetched = re.fullmatch(r'Fetched .+ from (https?://\S+)', output)
                    if url and event.get('status') == 'success' and fetched:
                        actual_url = fetched.group(1)
                        ResearchSource(title='Opened source', url=actual_url)
                        opened.add(actual_url)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return opened
