from datetime import datetime, timezone
from types import SimpleNamespace

def test_extracts_multiple_discord_links():
    from vid2idea.capture import extract_links
    assert extract_links('Try <https://example.com/a> and https://example.com/b. ftp://example.com/c') == ['https://example.com/a', 'https://example.com/b']

def test_capture_filters_channel_author_and_bots():
    from vid2idea.capture import capture_message
    from vid2idea.config import Settings
    settings = Settings(discord_channel_id='123456789012345678', discord_author_id='223456789012345678')  # Synthetic test IDs; gitleaks:allow
    message = SimpleNamespace(channel=SimpleNamespace(id=123456789012345678), author=SimpleNamespace(id=223456789012345678, bot=False), id=323456789012345678, content='Make this https://example.com/a', created_at=datetime.now(timezone.utc))
    assert len(capture_message(message, settings)) == 1
    message.author.bot = True
    assert capture_message(message, settings) == []
    message.author.bot = False
    message.author.id = 423456789012345678
    assert capture_message(message, settings) == []
    message.author.id = 223456789012345678
    message.channel.id = 523456789012345678
    assert capture_message(message, settings) == []
