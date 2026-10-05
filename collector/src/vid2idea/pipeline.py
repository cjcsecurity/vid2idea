"""A disposable process isolates media/model work and its temporary files."""
import json
import os
import signal
import subprocess
import sys
import time
from .ai import generate_brief
from .articles import read_article
from .cloud import publication_payload
from .config import Settings
from .models import SourceCapture
from .urls import SourceError
from .videos import is_video_url, media_workspace, read_video
from .media_assets import prepare_image_uploads
from .research import research_questions
from .environment import runtime_environment


def process_capture(capture, settings):
    deadline=time.monotonic()+900
    # Parent owns the workspace: even a killed child cannot leave raw media behind.
    with media_workspace(settings.data_dir) as workdir:
        config = settings.model_dump(mode='json')
        # Pydantic's ordinary serialization redacts secrets; explicitly pass only the
        # model credential via stdin to the isolated process, never on its command line.
        config['ai_api_key'] = settings.ai_api_key.get_secret_value()
        config['discord_token'] = ''
        config['supabase_secret_key'] = ''
        config['notion_api_token'] = ''
        payload = json.dumps({'capture':capture.model_dump(mode='json'),'settings':config,'workdir':str(workdir),'deadline':deadline})
        environment = {**runtime_environment(), 'NO_PROXY':'', 'no_proxy':''}
        child = subprocess.Popen([sys.executable,'-m','vid2idea.pipeline'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True,env=environment)
        try:
            stdout, _ = child.communicate(payload, timeout=max(0,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            raise SourceError('job_timeout', transient=True) from None
        except BaseException:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            raise
        try:
            output = json.loads(stdout)
        except ValueError:
            raise SourceError('processor_failed') from None
        if 'error' in output:
            raise SourceError(output['error'], output.get('transient',False), output.get('retry_after'))
        return output['result']


def main():
    from pathlib import Path
    try:
        request = json.load(sys.stdin)
        capture = SourceCapture.model_validate(request['capture'])
        settings = Settings.model_validate(request['settings'])
        if is_video_url(capture.canonical_url):
            evidence = read_video(capture.canonical_url,settings,Path(request['workdir']))
        else:
            evidence = read_article(capture.canonical_url,settings,Path(request['workdir']))
        generated = generate_brief(evidence,capture.note,settings)
        deadline=request.get('deadline',time.monotonic()+900)
        evidence.gaps.extend(research_questions(generated,settings,evidence,deadline=deadline))
        status = 'partial' if any('could not' in gap.lower() or 'waiting' in gap.lower() for gap in evidence.gaps) else 'ready'
        result=publication_payload(generated,evidence,status)
        result['image_uploads']=prepare_image_uploads(evidence.images)
        print(json.dumps({'result':result}))
    except SourceError as error:
        print(json.dumps({'error':error.code,'transient':error.transient,'retry_after':error.retry_after}))
    except Exception:
        print(json.dumps({'error':'processor_failed'}))

if __name__ == '__main__':
    main()
