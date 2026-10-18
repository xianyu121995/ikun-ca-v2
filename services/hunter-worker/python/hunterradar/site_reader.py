"""Read a project's official site and its docs/whitepaper page as plain text for the AI prefill
(owner decision 2026-10-18). Read-only GETs, size/time limited, public hosts only, never raises."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 1_500_000
DOC_HINT = re.compile(r'(docs?|documentation|whitepaper|white-paper|litepaper|lightpaper|gitbook|notion\.site|wiki|learn|about)', re.I)
DOC_HOSTS = ('gitbook.io', 'notion.site', 'mirror.xyz', 'medium.com', 'paragraph.xyz', 'substack.com')
BIO_DOMAIN = re.compile(r'(?<![@\w])((?:[a-z0-9-]+\.)+(?:com|io|xyz|fun|finance|app|org|net|ai|gg|so|co|dev|money|trade|network|fi|art|world|club|me|tech|game|games|exchange|capital|labs|market))\b', re.I)


def public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


def bio_domains(bio: str):
    return [d.lower().removeprefix('www.') for d in BIO_DOMAIN.findall(bio or '')]


def _text(raw: str):
    title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.I | re.S)
    meta = re.search(r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]+content=["\']([^"\']*)', raw, re.I)
    body = re.sub(r'(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>', ' ', raw)
    body = re.sub(r'(?s)<[^>]+>', ' ', body)
    body = re.sub(r'\s+', ' ', html.unescape(body)).strip()
    parts = [html.unescape(x.group(1)).strip() for x in (title, meta) if x]
    return ' | '.join(p for p in parts + [body] if p)


def fetch(url: str, proxy: str | None, timeout=12.0):
    """Returns (final_url, html_text) or (None, '')."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or not public_host(parts.hostname):
            return None, ''
        with httpx.Client(proxy=proxy, timeout=timeout, follow_redirects=True, max_redirects=4,
                          headers={'User-Agent': 'Mozilla/5.0 (Macintosh) ikun-research/1.0', 'Accept': 'text/html'}) as client:
            with client.stream('GET', url) as response:
                final = str(response.url)
                host = urlsplit(final).hostname or ''
                if response.status_code != 200 or 'html' not in response.headers.get('content-type', '') or not public_host(host):
                    return None, ''
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk); chunks.append(chunk)
                    if size > MAX_BYTES:
                        break
                return final, b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')
    except (httpx.HTTPError, ValueError, UnicodeError, OSError):
        return None, ''


def doc_links(base: str, raw: str, extra=()):
    found = []
    for href in re.findall(r'<a[^>]+href=["\']([^"\'#]+)', raw, re.I):
        url = urljoin(base, href.strip())
        if url.startswith('http') and DOC_HINT.search(url) and not url.lower().endswith('.pdf') and url not in found:
            found.append(url)
    for url in extra:
        host = (urlsplit(url).hostname or '').lower()
        if any(host == h or host.endswith('.' + h) for h in DOC_HOSTS) and url not in found:
            found.insert(0, url)
    return found[:3]


def read_project(domain: str | None, proxy: str | None, tweet_links=()):
    """Returns {'site': text, 'docs': text, 'docs_url': str|None} (texts trimmed for the prompt)."""
    out = {'site': '', 'docs': '', 'docs_url': None}
    raw, base = '', None
    if domain:
        base, raw = fetch('https://' + domain, proxy)
        out['site'] = _text(raw)[:3500] if raw else ''
    for url in doc_links(base or '', raw, tweet_links):
        final, doc = fetch(url, proxy)
        if doc:
            text = _text(doc)
            if len(text) > 200:
                out['docs'], out['docs_url'] = text[:5000], final
                break
    return out
