import json
import time
from datetime import datetime, timedelta, timezone
from .pipeline import process_capture
from .urls import SourceError
from .notion_api import PublicationError


def event(name, entry_point, **fields):
    print(json.dumps({'event':name,'entry_point':entry_point,**fields}), flush=True)


class Worker:
    def __init__(self, outbox, cloud, settings, processor=process_capture, entry_point='run'):
        self.outbox, self.cloud, self.settings, self.processor = outbox, cloud, settings, processor
        self.entry_point = entry_point
        self.last_error_code = None

    def run_once(self, now=None):
        now = now or datetime.now(timezone.utc)
        job = self.outbox.claim(now)
        if not job:
            return 'idle'
        started = time.monotonic()
        event('job_started', self.entry_point, job_id=job.id, attempt=job.retry_count+1)
        try:
            if not job.idea_id:
                job.idea_id = self.cloud.ingest(job.capture)
                self.outbox.save(job)
            if not job.retry_request_id and not job.cached_result and self.cloud.is_finished(job.idea_id):
                self.outbox.complete(job.id)
                return 'processed'
            if not job.cached_result:
                if not self.settings.ai_configured:
                    self.cloud.status(job.idea_id,'queued','ai_not_configured')
                    raise SourceError('ai_not_configured', transient=True, retry_after=300)
                self.cloud.status(job.idea_id, 'processing')
                job.cached_result = self.processor(job.capture, self.settings)
                self.outbox.save(job)
            self.cloud.publish_payload(job.idea_id, job.cached_result)
            if job.retry_request_id:
                self.cloud.acknowledge_retry(job.idea_id, job.retry_request_id)
            self.outbox.complete(job.id)
            self.last_error_code = None
            event('job_completed',self.entry_point,job_id=job.id,duration_seconds=round(time.monotonic()-started,2))
            return 'processed'
        except Exception as error:
            if isinstance(error, PublicationError):
                code, transient, delay = error.code, True, error.retry_after
            elif isinstance(error, SourceError):
                code, transient, delay = error.code, error.transient, error.retry_after
            else:
                code, transient, delay = 'cloud_unavailable', True, None
            self.last_error_code = code
            # Missing configuration never consumes the finite transient retry budget.
            if isinstance(error, PublicationError) or code == 'cloud_unavailable':
                # Sync failures cannot discard a result or consume paid/model work.
                # Keep retrying the same publication slowly while the cloud is down.
                self.outbox.defer(job.id,code,now+timedelta(seconds=max(60,delay or 0)))
                result = 'rescheduled'
            elif code == 'ai_not_configured' or code in (
                'codex_not_installed','codex_subscription_login_required',
                'claude_not_installed','claude_subscription_login_required','claude_unsupported_version',
                'gemini_not_installed','gemini_unsupported_version','gemini_login_required',
            ):
                self.outbox.defer(job.id,code,now+timedelta(seconds=300))
                result = 'rescheduled'
            elif transient and job.retry_count < 4:
                self.outbox.reschedule(job.id,code,now+timedelta(seconds=max(delay or 0,min(30*2**job.retry_count,600))))
                result = 'rescheduled'
            else:
                # Persist the failure payload before trying cloud publication. A network
                # failure here keeps a durable publish job instead of losing the error.
                terminal_status = 'failed' if transient or code in ('invalid_model_output','processor_failed') else 'blocked'
                job.cached_result = {'processing_status':terminal_status,'error_code':code}
                self.outbox.save(job)
                try:
                    if job.idea_id:
                        self.cloud.publish_payload(job.idea_id,job.cached_result)
                    if job.retry_request_id:
                        self.cloud.acknowledge_retry(job.idea_id,job.retry_request_id)
                    self.outbox.fail(job.id,code)
                except Exception:
                    self.outbox.defer(job.id,code,now+timedelta(seconds=600))
                result = 'blocked'
            event('job_deferred' if result == 'rescheduled' else 'job_blocked',self.entry_point,job_id=job.id,error_code=code,attempt=job.retry_count+1,duration_seconds=round(time.monotonic()-started,2))
            return result
