from .models import Evidence, EvidenceKind, EvidenceLink, EvidenceImage, Resource
from urllib.parse import urljoin
from .safe_proxy import SafeProxy
from .urls import SourceError, validate_public_url


def evidence_from_html(html: str, source_url: str = '') -> Evidence:
    from scrapling.parser import Selector
    from scrapling.core.shell import Convertor
    page = Selector(html)
    selector = 'article, main, [role="main"]' if page.css('article, main, [role="main"]') else None
    text = '\n'.join(Convertor._extract_content(page, extraction_type='text', css_selector=selector, main_content_only=True)).strip()
    if len(text) < 30:
        raise SourceError('empty_article')
    links=[]
    for anchor in page.css('article a[href], main a[href], [role="main"] a[href]' if selector else 'a[href]'):
        target=urljoin(source_url,anchor.attrib.get('href',''))
        try:
            Resource(name='Article link',url=target,summary='Linked in the article.')
        except ValueError:
            continue
        name=anchor.get_all_text().strip()[:200]
        if name and target not in {link.url for link in links}:
            links.append(EvidenceLink(name=name,url=target))
        if len(links)>=80:
            break
    return Evidence(text=text[:48000], kinds=[EvidenceKind.article_text],source_url=source_url,links=links)


def article_image_candidates(html, source_url):
    from scrapling.parser import Selector
    page=Selector(html);result=[]
    for node in page.css('meta[property="og:image"], meta[name="twitter:image"], article img[src], main img[src]'):
        target=urljoin(source_url,node.attrib.get('content') or node.attrib.get('src') or '')
        if not target.startswith(('http://','https://')) or target in {image['url'] for image in result}:
            continue
        result.append({'url':target,'caption':(node.attrib.get('alt') or 'Image from the source article')[:300]})
        if len(result)>=3:
            break
    return result


def read_article(url, settings, workdir=None):
    import os
    from scrapling.fetchers import Fetcher
    from scrapling.core.utils import log
    import logging
    log.setLevel(logging.CRITICAL)  # upstream logs include raw/signed URLs
    # This reader runs in a disposable processing process. libcurl otherwise
    # honors proxy exclusions even when an explicit safety proxy is supplied.
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = ''
    url = validate_public_url(url)
    with SafeProxy(byte_limit=4 * 1024 * 1024, seconds=90) as proxy:
        try:
            page = Fetcher.get(url, proxy=proxy.url, follow_redirects='safe', timeout=30, retries=0, stealthy_headers=False)
        except Exception:
            raise proxy.error or SourceError('article_unavailable', transient=True) from None
        if page.status in (401, 403):
            raise SourceError('source_requires_access')
        if page.status == 429 or page.status >= 500:
            raise SourceError('source_busy', transient=True)
        if page.status != 200:
            raise SourceError('article_unavailable')
        document_url=validate_public_url(str(page.url))
        evidence=evidence_from_html(page.html_content,document_url)
    if workdir is not None:
        import httpx
        candidates=article_image_candidates(page.html_content,document_url)
        with SafeProxy(byte_limit=6*1024*1024,seconds=60) as proxy:
            with httpx.Client(proxy=proxy.url,trust_env=False,follow_redirects=True,timeout=20) as client:
                for index,item in enumerate(candidates):
                    try:
                        validate_public_url(item['url'])
                        with client.stream('GET',item['url']) as response:
                            if response.status_code!=200:
                                continue
                            content=bytearray()
                            for chunk in response.iter_bytes():
                                content.extend(chunk)
                                if len(content)>4*1024*1024:
                                    raise SourceError('download_limit')
                        path=workdir/f'article-image-{index}.bin';path.write_bytes(content)
                        evidence.images.append(EvidenceImage(path=path,caption=item['caption']))
                    except Exception:
                        continue
        if candidates and not evidence.images:
            evidence.gaps.append('Source images could not be retrieved.')
    return evidence
