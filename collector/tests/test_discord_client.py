from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from vid2idea.config import Settings
from vid2idea.discord_client import IdeaClient
from vid2idea.outbox import Outbox


@pytest.mark.asyncio
async def test_history_retries_from_last_durable_message(monkeypatch, tmp_path):
    box = Outbox(tmp_path / 'outbox.sqlite')
    settings = Settings(discord_channel_id='123456789012345678')  # Synthetic test ID; gitleaks:allow
    client = IdeaClient(settings, box)
    state = {'attempts': 0, 'closed': False}
    cursors, delays, health = [], [], []

    def message(number):
        return SimpleNamespace(id=number, channel=SimpleNamespace(id=int(settings.discord_channel_id)),
            author=SimpleNamespace(id=223456789012345678, bot=False),
            content=f'https://example.com/{number}', created_at=datetime.now(timezone.utc))

    async def history(**kwargs):
        state['attempts'] += 1
        cursors.append(kwargs['after'].id if kwargs['after'] else None)
        if state['attempts'] == 1:
            yield message(323456789012345678)
            raise OSError('temporary disconnect')
        yield message(423456789012345678)

    async def sleep(delay):
        delays.append(delay)
        health.append(client.history_error)
        if state['attempts'] == 2:
            state['closed'] = True

    monkeypatch.setattr(client, 'fetch_channel', AsyncMock(return_value=SimpleNamespace(history=history)))
    monkeypatch.setattr(client, 'wait_until_ready', AsyncMock())
    monkeypatch.setattr(client, 'is_closed', lambda: state['closed'])
    monkeypatch.setattr('vid2idea.discord_client.asyncio.sleep', sleep)
    try:
        await client.history_loop()
        assert cursors == [None, 323456789012345678]
        assert box.pending_count() == 2
        assert box.cursor(settings.discord_channel_id) == '423456789012345678'
        assert health == ['discord_history_unavailable', None]
        assert 0 < delays[0] <= 300
    finally:
        box.close()


@pytest.mark.asyncio
async def test_history_failure_is_visible_in_heartbeat(monkeypatch):
    cloud = SimpleNamespace(record_status=Mock())
    box = SimpleNamespace(pending_count=lambda: 0)
    client = IdeaClient(Settings(), box, cloud, SimpleNamespace(last_error_code=None))
    client.history_error = 'discord_history_unavailable'
    state = {'closed': False}
    monkeypatch.setattr(client, 'wait_until_ready', AsyncMock())
    monkeypatch.setattr(client, 'is_closed', lambda: state['closed'])
    async def sleep(_):
        state['closed'] = True
    monkeypatch.setattr('vid2idea.discord_client.asyncio.sleep', sleep)
    await client.heartbeat_loop()
    cloud.record_status.assert_called_once_with(0, 'discord_history_unavailable')


def test_failed_history_import_returns_nonzero(monkeypatch, tmp_path):
    from vid2idea import cli
    settings = Settings(discord_channel_id='123456789012345678', discord_token='test-token',  # Synthetic test values; gitleaks:allow
        supabase_url='https://example.supabase.co', supabase_secret_key='test-secret',
        owner_id='00000000-0000-4000-8000-000000000001', data_dir=tmp_path)
    monkeypatch.setattr(cli.Settings, 'from_env', lambda: settings)
    monkeypatch.setattr('vid2idea.cloud.CloudStore', lambda _: SimpleNamespace())
    monkeypatch.setattr('vid2idea.discord_client.IdeaClient',
        lambda *args, **kwargs: SimpleNamespace(run=lambda *args, **kwargs: None,
            history_error='discord_history_unavailable'))
    monkeypatch.setattr('sys.argv', ['vid2idea', 'import-history'])
    assert cli.main() == 1


@pytest.mark.asyncio
async def test_refresh_poll_failure_does_not_prevent_worker(monkeypatch):
    cloud=SimpleNamespace(list_retry_requests=Mock(side_effect=OSError()))
    worker=SimpleNamespace(run_once=Mock(return_value='processed'))
    box=SimpleNamespace(pending_count=lambda:0)
    client=IdeaClient(Settings(),box,cloud,worker)
    state={'closed':False}
    monkeypatch.setattr(client,'wait_until_ready',AsyncMock())
    monkeypatch.setattr(client,'is_closed',lambda:state['closed'])
    async def sleep(_): state['closed']=True
    monkeypatch.setattr('vid2idea.discord_client.asyncio.sleep',sleep)
    await client.work_loop()
    worker.run_once.assert_called_once()
