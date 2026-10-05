"""Creates two temporary accounts, exercises real authorization, then cleans up.

Set TEST_SUPABASE_URL, TEST_SUPABASE_SECRET_KEY, TEST_SUPABASE_PUBLISHABLE_KEY.
Use a dedicated test project with the migration applied, never an arbitrary target.
"""
import os
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from supabase import create_client

pytestmark = pytest.mark.live

@pytest.fixture
def clients():
    names = ['TEST_SUPABASE_URL','TEST_SUPABASE_SECRET_KEY','TEST_SUPABASE_PUBLISHABLE_KEY']
    if not all(os.getenv(n) for n in names):
        pytest.fail('Live tests require the three TEST_SUPABASE_* settings')
    url,secret,key = (os.environ[n] for n in names)
    admin, anon = create_client(url,secret), create_client(url,key)
    accounts = []
    try:
        for _ in range(2):
            email,password = f'vid2idea-test-{uuid4()}@example.com', str(uuid4())+'aA9!'
            user = admin.auth.admin.create_user({'email':email,'password':password,'email_confirm':True}).user
            accounts.append((user.id,create_client(url,key)))
            accounts[-1][1].auth.sign_in_with_password({'email':email,'password':password})
        yield admin,anon,accounts
    finally:
        for user_id,_ in accounts:
            bucket = admin.storage.from_('idea-images')
            for folder in bucket.list(user_id):
                prefix = user_id+'/'+folder['name']
                paths = [prefix+'/'+item['name'] for item in bucket.list(prefix)]
                if paths:
                    bucket.remove(paths)
            admin.auth.admin.delete_user(user_id)

def test_private_source_images_owner_only_and_collector_only_writes(clients):
    import io
    from PIL import Image
    from vid2idea.cloud import CloudStore
    from vid2idea.models import EvidenceImage
    from vid2idea.media_assets import prepare_image_uploads
    from tempfile import TemporaryDirectory
    from pathlib import Path
    admin,anon,accounts = clients
    owner,reader = accounts[0]
    _,outsider = accounts[1]
    capture = {'canonical_url':'https://example.com/'+str(uuid4()),'original_url':'https://example.com/image','channel_id':'test','message_id':str(uuid4()),'shared_at':datetime.now(timezone.utc).isoformat()}
    idea = admin.rpc('ingest_source',{'p_owner_id':owner,'p_capture':capture}).execute().data
    cloud = CloudStore.__new__(CloudStore)
    cloud.owner_id,cloud.client = owner,admin
    with TemporaryDirectory() as directory:
        image = Path(directory)/'source.png'
        Image.new('RGB',(40,40),'orange').save(image)
        uploads = prepare_image_uploads([EvidenceImage(path=image,caption='Test source')])
    cloud.publish_payload(idea,{'title':'Image test','image_uploads':uploads,'processing_status':'ready'})
    row = reader.table('ideas').select('images').eq('id',idea).single().execute().data
    path = row['images'][0]['path']
    assert Image.open(io.BytesIO(reader.storage.from_('idea-images').download(path))).size == (40,40)
    for client in [anon,outsider]:
        with pytest.raises(Exception):
            client.storage.from_('idea-images').download(path)
    with pytest.raises(Exception):
        reader.storage.from_('idea-images').upload(owner+'/'+idea+'/forbidden.jpg',b'forbidden',{'content-type':'image/jpeg'})
    cloud.status(idea,'processing')
    assert reader.table('ideas').select('images').eq('id',idea).single().execute().data['images'] == row['images']

def test_privacy_idempotency_personal_fields_and_retry(clients):
    admin,anon,accounts = clients
    owner,reader = accounts[0]
    other,outsider = accounts[1]
    capture = {'channel_id':'123456789012345678','message_id':'223456789012345678','original_url':'https://example.com/'+str(uuid4()),'note':'Try this','shared_at':datetime.now(timezone.utc).isoformat()}
    capture['canonical_url'] = capture['original_url']
    params = {'p_owner_id':owner,'p_capture':capture}
    idea = admin.rpc('ingest_source',params).execute().data
    assert admin.rpc('ingest_source',params).execute().data == idea
    assert len(admin.table('source_shares').select('id').eq('idea_id',idea).execute().data) == 1
    with pytest.raises(Exception):
        anon.table('ideas').select('id').execute()
    assert outsider.table('ideas').select('id').eq('id',idea).execute().data == []
    outsider.table('ideas').update({'personal_notes':'intrusion'}).eq('id',idea).execute()
    reader.table('ideas').update({'personal_notes':'My notes','favorite':True,'stage':'trying'}).eq('id',idea).execute()
    with pytest.raises(Exception):
        reader.table('ideas').update({'title':'unauthorized'}).eq('id',idea).execute()
    with pytest.raises(Exception):
        reader.rpc('publish_brief',{'p_idea_id':idea,'p_generated':{'title':'unauthorized'}}).execute()
    with pytest.raises(Exception):
        outsider.rpc('request_retry',{'p_idea_id':idea}).execute()
    publish = {'p_idea_id':idea,'p_generated':{'title':'Garden','brief':{'summary':'A garden'},'processing_status':'ready'}}
    admin.rpc('publish_brief',publish).execute()
    row = reader.table('ideas').select('*').eq('id',idea).single().execute().data
    assert (row['personal_notes'],row['favorite'],row['stage']) == ('My notes',True,'trying')
    reader.rpc('request_retry',{'p_idea_id':idea}).execute()
    a = reader.table('ideas').select('retry_request_id').eq('id',idea).single().execute().data['retry_request_id']
    reader.rpc('request_retry',{'p_idea_id':idea}).execute()
    assert reader.table('ideas').select('retry_request_id').eq('id',idea).single().execute().data['retry_request_id'] == a
    admin.rpc('acknowledge_retry',{'p_idea_id':idea,'p_request_id':str(uuid4())}).execute()
    assert reader.table('ideas').select('retry_request_id').eq('id',idea).single().execute().data['retry_request_id'] == a
    admin.rpc('publish_brief',{'p_idea_id':idea,'p_generated':{'processing_status':'processing'}}).execute()
    with pytest.raises(Exception):
        reader.rpc('request_retry',{'p_idea_id':idea}).execute()
