"""Small setup operations, usable from both a source checkout and an installed wheel."""
import os
from importlib.resources import files
from pathlib import Path

from .config import ConfigurationError


def initialize_config(path: Path):
    template = files('vid2idea').joinpath('env.example').read_text(encoding='utf-8')
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise ConfigurationError('Configuration already exists. It was left unchanged.') from None
    except OSError:
        raise ConfigurationError('Cannot create configuration. Check the destination directory and permissions.') from None
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(template)
        handle.flush()
        os.fsync(handle.fileno())


def discover_sources(settings, *, transport=None):
    from .notion_api import NotionAPI, PublicationError
    if not settings.notion_api_token.get_secret_value():
        raise ConfigurationError('Set NOTION_API_TOKEN locally, then grant the connection access to Library and Projects.')
    api = NotionAPI(settings, transport=transport)
    result, seen, cursor = [], set(), None
    try:
        for _ in range(10):
            body = {'filter': {'property': 'object', 'value': 'data_source'}, 'page_size': 100}
            if cursor:
                body['start_cursor'] = cursor
            data = api.request('POST', '/search', json=body)
            for item in data['results']:
                result.append({'name': ''.join(part.get('plain_text', '') for part in item.get('title', [])), 'data_source_id': item['id']})
            if not data.get('has_more'):
                return result
            cursor = data.get('next_cursor')
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
        raise PublicationError('notion_search_limit')
    finally:
        api.close()
