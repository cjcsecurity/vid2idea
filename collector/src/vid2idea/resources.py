"""Resource links must come from observed source text or article anchors."""
import re
from urllib.parse import urlsplit
from .models import Resource

URL_TEXT = re.compile(r'(?<![@\w])(?:https?://[^\s<>"\[\]]+|[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,63}(?![a-zA-Z0-9-]|\.[a-zA-Z0-9])(?:/[^\s<>"\[\]]*)?)', re.I)


def observed_urls(text):
    result = []
    for match in URL_TEXT.finditer(text):
        url = match.group().rstrip('.,;:)\'')
        if not url.lower().startswith(('http://','https://')):
            url = 'https://' + url
        try:
            Resource(name='Observed resource',url=url,summary='Observed in source evidence.')
        except ValueError:
            continue
        if url not in result:
            result.append(url)
    return result[:80]


def link_key(url):
    parsed=urlsplit(url)
    return (parsed.hostname or '').lower(),parsed.path.rstrip('/'),parsed.query


def finalize_generated(result, evidence, projects):
    allowed = {link_key(url) for url in observed_urls(evidence.text+'\n'+evidence.ocr_text)}
    allowed.update(link_key(link.url) for link in evidence.links)
    if evidence.source_url:
        allowed.add(link_key(evidence.source_url))
    for resource in result.brief.resources:
        if resource.url and link_key(resource.url) not in allowed:
            resource.url = None
    names = {project['name'] for project in projects}
    for use in result.brief.use_cases:
        if use.kind == 'project' and use.project not in names:
            use.kind, use.project = 'general', None
        if use.kind == 'general':
            use.project = None
    return result
