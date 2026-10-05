import re
from .models import SourceCapture
from .urls import canonicalize_url, SourceError


def extract_links(content: str) -> list[str]:
    links = []
    for match in re.finditer(r'https?://[^\s<>]+', content):
        url = match.group().rstrip('.,;!?:\"\'')
        while url.endswith(')') and url.count(')') > url.count('('):
            url = url[:-1]
        if url not in links:
            links.append(url)
    return links


def capture_message(message, settings) -> list[SourceCapture]:
    if str(message.channel.id) != settings.discord_channel_id or (settings.discord_author_id and str(message.author.id) != settings.discord_author_id) or message.author.bot:
        return []
    captures = []
    links = extract_links(message.content)
    note = message.content
    for link in links:
        note = note.replace(link, '')
    note = note.replace('<>', '').strip()[:4000]
    for link in links:
        try:
            canonical = canonicalize_url(link)
            captures.append(SourceCapture(channel_id=str(message.channel.id), message_id=str(message.id), original_url=link, canonical_url=canonical, note=note, shared_at=message.created_at))
        except (SourceError, ValueError):
            continue
    return captures
