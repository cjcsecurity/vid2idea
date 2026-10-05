from datetime import datetime, timezone
import base64
import hashlib
import json
from uuid import UUID
from supabase import create_client, ClientOptions
from .models import SourceCapture, RetryRequest

PUBLICATION_FIELDS = {'title','brief','tags','evidence_kinds','evidence_text','evidence_gaps','processing_status','error_code','images'}

def publication_payload(generated, evidence, status):
    return {**generated.model_dump(mode='json'), 'evidence_kinds': [str(k) for k in evidence.kinds], 'evidence_text': evidence.text, 'evidence_gaps': evidence.gaps, 'processing_status': str(status), 'error_code': None}

def validate_publication(payload):
    if not set(payload) <= PUBLICATION_FIELDS:
        raise ValueError('Unsupported publication fields')

class CloudStore:
    def __init__(self, settings):
        self.owner_id = settings.owner_id
        self.client = create_client(settings.supabase_url, settings.supabase_secret_key.get_secret_value(), options=ClientOptions(postgrest_client_timeout=30))

    def ingest(self, capture):
        return self.client.rpc('ingest_source', {'p_owner_id': self.owner_id, 'p_capture': capture.model_dump(mode='json')}).execute().data

    def publish_payload(self, idea_id, payload):
        # Never mutate the durable outbox result: network retries reuse these bytes.
        published = dict(payload)
        uploads = published.pop('image_uploads', None)
        validate_publication(published)
        bucket = None
        prefix = None
        if uploads is not None:
            if not isinstance(uploads, list) or len(uploads) > 3:
                raise ValueError('Invalid image uploads')
            prefix = f'{UUID(str(self.owner_id))}/{UUID(str(idea_id))}'
            prepared = []
            for item in uploads:
                data = base64.b64decode(item['data'], validate=True)
                if not data.startswith(b'\xff\xd8\xff') or len(data) > 204800 or hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Invalid source image')
                prepared.append((f"{prefix}/{item['sha256']}.jpg", data, item))
            bucket = self.client.storage.from_('idea-images')
            published['images'] = []
            for path, data, item in prepared:
                bucket.upload(path, data, {'content-type':'image/jpeg','upsert':'true'})
                published['images'].append({'path':path,'caption':item.get('caption','Source image')[:300],'timestamp_seconds':item.get('timestamp_seconds')})
        self.client.rpc('publish_brief', {'p_idea_id':idea_id, 'p_generated':published}).execute()
        if bucket is not None:
            # Publish first so a failed upload never breaks the existing brief.
            try:
                current = {item['path'] for item in published['images']}
                old = [f"{prefix}/{item['name']}" for item in bucket.list(prefix, {'limit':1000}) if item.get('name') and f"{prefix}/{item['name']}" not in current]
                if old:
                    bucket.remove(old)
            except Exception:
                print(json.dumps({'event':'image_cleanup_deferred','entry_point':'publish'}), flush=True)

    def publish(self, idea_id, generated, evidence, status):
        self.publish_payload(idea_id, publication_payload(generated, evidence, status))

    def status(self, idea_id, status, code=None):
        self.publish_payload(idea_id, {'processing_status':str(status), 'error_code':code})

    def is_finished(self, idea_id):
        rows = self.client.table('ideas').select('processing_status').eq('id',idea_id).eq('owner_id',self.owner_id).execute().data
        return bool(rows and rows[0]['processing_status'] in ('ready','partial'))

    def list_retry_requests(self):
        ideas = self.client.table('ideas').select('id,canonical_url,retry_request_id,retry_requested_at').eq('owner_id',self.owner_id).not_.is_('retry_request_id','null').limit(50).execute().data
        result = []
        for idea in ideas:
            shares = self.client.table('source_shares').select('channel_id,message_id,original_url,note,shared_at').eq('idea_id',idea['id']).eq('owner_id',self.owner_id).order('shared_at').limit(1).execute().data
            if shares:
                capture = SourceCapture(**shares[0], canonical_url=idea['canonical_url'])
                result.append(RetryRequest(id=idea['retry_request_id'], idea_id=idea['id'], capture=capture, requested_at=idea['retry_requested_at']))
        return result

    def acknowledge_retry(self, idea_id, request_id):
        self.client.rpc('acknowledge_retry', {'p_idea_id':idea_id,'p_request_id':request_id}).execute()

    def record_status(self, pending_count, last_error_code=None):
        self.client.table('collector_status').upsert({'owner_id':self.owner_id,'last_seen_at':datetime.now(timezone.utc).isoformat(),'pending_count':pending_count,'last_error_code':last_error_code}).execute()
