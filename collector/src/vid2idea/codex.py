"""Brief generation through the user's normal, ChatGPT-authenticated Codex CLI."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from .ai import SYSTEM, evidence_payload
from .project_context import load_project_context
from .resources import finalize_generated
from .models import GeneratedBrief, EvidenceKind
from .urls import SourceError
from .environment import runtime_environment


def strict_schema(value):
    if isinstance(value, dict):
        value.pop('default',None)
        if value.get('type') == 'object':
            value['additionalProperties'] = False
            value['required'] = list(value.get('properties',{}))
        for child in value.values():
            strict_schema(child)
    elif isinstance(value,list):
        for child in value:
            strict_schema(child)
    return value


def run_codex(prompt, output_model, settings, *, frames=(), search=False, timeout=240):
    deadline=time.monotonic()+timeout
    if not shutil.which(settings.codex_command):
        raise SourceError('codex_not_installed',transient=True,retry_after=300)
    environment = runtime_environment()
    try:
        login = subprocess.run([settings.codex_command,'login','status'],capture_output=True,text=True,timeout=min(15,timeout),env=environment)
        if login.returncode or 'logged in using chatgpt' not in (login.stdout + login.stderr).lower():
            raise SourceError('codex_subscription_login_required',transient=True,retry_after=300)
    except (OSError,subprocess.TimeoutExpired):
        raise SourceError('codex_unavailable',transient=True) from None
    with TemporaryDirectory(prefix='vid2idea-codex-') as directory:
        root = Path(directory)
        schema,output = root/'schema.json',root/'brief.json'
        schema.write_text(json.dumps(strict_schema(output_model.model_json_schema())))
        args = [settings.codex_command,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
            '--sandbox','read-only','--color','never','--cd',str(root),
            '--output-schema',str(schema),'--output-last-message',str(output),
            '-c','approval_policy="never"','-c',f'web_search="{"live" if search else "disabled"}"','-c','project_doc_max_bytes=0']
        # Isolate this text/vision task from the user's connected tools and coding
        # environment. Files arrive only as explicit image attachments.
        for feature in ('shell_tool','unified_exec','apps','plugins','multi_agent','browser_use','browser_use_external','computer_use','view_image','skill_search','workspace_dependencies','skill_mcp_dependency_install'):
            args += ['-c',f'features.{feature}=false']
        # Codex 0.160 routes its hosted web tool through Code Mode. Its JS host
        # exposes only the remaining web tool; shell/apps/local tools stay off.
        args += ['-c',f'features.code_mode_host={"true" if search else "false"}']
        args += ['-c','features.skip_host_skill_discovery=true']
        if settings.codex_model:
            args += ['--model',settings.codex_model]
        if search:
            args += ['--json']
        for frame in frames:
            args += ['-i',str(frame.resolve())]
        args += ['-']
        # Preserve the normal Codex authentication location without copying, reading,
        # or logging its tokens. Collector/service credentials are not inherited.
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise SourceError('codex_unavailable',transient=True)
            trace_path = root/'events.jsonl'
            with trace_path.open('w') as trace_file:
                completed = subprocess.run(args,input=prompt,text=True,stdout=trace_file if search else subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=remaining,env=environment)
        except (OSError,subprocess.TimeoutExpired):
            raise SourceError('codex_unavailable',transient=True) from None
        if completed.returncode or not output.exists():
            raise SourceError('codex_unavailable',transient=True)
        if output.stat().st_size > 256*1024 or trace_path.stat().st_size > 4*1024*1024:
            raise SourceError('invalid_model_output')
        try:
            result = output_model.model_validate_json(output.read_text())
        except ValueError:
            raise SourceError('invalid_model_output') from None
        trace = trace_path.read_text() if search else ''
    return result, trace


def generate_with_codex(evidence, note, settings):
    if not evidence.text.strip() and not evidence.frames:
        raise SourceError('no_readable_evidence')
    projects = load_project_context(settings)
    prompt = SYSTEM + '\nReturn the brief directly. Do not use tools or inspect files.\n' + json.dumps(evidence_payload(evidence,note,settings,projects))
    result, _ = run_codex(prompt, GeneratedBrief, settings, frames=evidence.frames)
    if evidence.frames:
        evidence.kinds.append(EvidenceKind.video_frames)
    return finalize_generated(result,evidence,projects)
