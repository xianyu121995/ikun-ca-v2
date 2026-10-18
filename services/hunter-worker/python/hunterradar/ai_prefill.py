"""AI Chinese prefill for new Hunter discoveries (owner decision 2026-10-18).

Suggestions are stored in the state table as 'ai:<discovery_id>' and only shown as a draft in the
drawer; nothing is saved to the project or tracked until the owner clicks save. No rating is suggested.
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from . import gemini

PREFIX = 'ai:'
PROMPT = (
    "你是加密货币/Web3 项目研究助手。根据下面 X 账号的名称和简介，用简体中文帮我预填项目资料。要求：\n"
    "资料包括：账号名称、简介、最近几条推文（tweets）、推文里出现过的外部链接（links），以及官网首页文字（site）和官网文档/白皮书页文字（docs，如有）。优先依据官网和文档判断项目具体做什么。\n"
    "- name：一句很短的中文项目名，概括它是做什么的、在哪条链上，风格例如“SOL上的AI审计发射台”“HYP高性能L2”“RWA农业游戏”，不超过 16 个字；看不出来就用原名。\n"
    "- website：从简介或 links 里挑出项目自己的官网域名（如 pindar.finance），不要选 x.com、t.co、linktr.ee、discord、telegram、github、medium 这类第三方站点，没有就给空字符串，不要编造。\n"
    "- description：两到三句中文简介，说明项目具体做什么（产品/机制/所在链）、进展到哪（如测试网/主网），依据官网文档、简介和推文，不要编造。\n"
    "- notes：一句中文备注，点出值得关注的信号（如代币、白名单、测试网、空投、NFT、即将上线），没有就给空字符串。\n"
    "只输出 JSON：{\"name\": ..., \"website\": ..., \"description\": ..., \"notes\": ...}\n\n"
)
DOMAIN = re.compile(r'^(?:https?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?:/\S*)?$', re.I)


def suggestion(db, discovery_id):
    row = db.execute('SELECT value FROM state WHERE key=?', (PREFIX + discovery_id,)).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row[0])
    except ValueError:
        return None
    return value if isinstance(value, dict) and value.get('name') else None


THIRD_PARTY = ('x.com', 'twitter.com', 't.co', 'linktr.ee', 'discord.gg', 'discord.com', 't.me', 'telegram.me', 'github.com',
               'medium.com', 'mirror.xyz', 'youtube.com', 'youtu.be', 'gitbook.io', 'notion.site', 'galxe.com', 'zealy.io')


def recent_tweets(settings, handle, limit=8):
    """Read-only 6551 lookup of a discovery's latest tweets (text + expanded links). Failures return []."""
    if settings is None or not getattr(settings, 'external_io_enabled', False) or not getattr(settings, 'token_6551', ''):
        return []
    try:
        with httpx.Client(timeout=15) as client:
            response = client.post('https://ai.6551.io/open/twitter_user_tweets',
                                   json={'username': handle, 'maxResults': limit, 'product': 'Latest',
                                         'includeReplies': False, 'includeRetweets': False},
                                   headers={'Authorization': 'Bearer ' + settings.token_6551})
        data = response.json().get('data') if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return []
    out = []
    for t in data if isinstance(data, list) else []:
        if not isinstance(t, dict) or not isinstance(t.get('text'), str):
            continue
        links = [u.get('url') for u in t.get('urls') or [] if isinstance(u, dict) and isinstance(u.get('url'), str)]
        out.append({'text': t['text'][:600], 'links': links[:5]})
    return out[:limit]


def link_domains(tweets):
    found = []
    for t in tweets:
        for link in t.get('links', []):
            host = (urlsplit(link).hostname or '').lower().removeprefix('www.')
            if host and not any(host == d or host.endswith('.' + d) for d in THIRD_PARTY) and host not in found:
                found.append(host)
    return found


def clean(value: dict, handle: str, bio: str, domains=()) -> dict:
    def text(key, limit):
        v = value.get(key)
        return v.strip()[:limit] if isinstance(v, str) else ''
    website = text('website', 200)
    match = DOMAIN.match(website)
    # Only keep a domain that actually appears in the bio (never invented).
    host = match.group(1).lower().removeprefix('www.') if match else ''
    website = ('https://' + host) if host and (host in bio.lower() or host in domains) else ''
    return {'name': text('name', 60) or handle, 'website': website, 'description': text('description', 600),
            'notes': text('notes', 300), 'generated_at': time.time()}


def run_pass(store, failures: dict, limit=3, settings=None) -> int:
    if not gemini.enabled():
        return 0
    from .formal import FormalService
    now = time.time()
    items = FormalService(store).page('signals', {'limit': '100'})['items']
    with store.connect() as db:
        done = {r[0][len(PREFIX):] for r in db.execute("SELECT key FROM state WHERE key LIKE 'ai:%'")}
    todo = [i for i in items if i['review_state'] == 'pending' and i['discovery_id'] not in done
            and failures.get(i['discovery_id'], 0) <= now][:limit]
    stored = 0
    for item in todo:
        bio = item.get('profile_bio') or ''
        tweets = recent_tweets(settings, item['x_handle'])
        domains = link_domains(tweets)
        from .site_reader import bio_domains, read_project
        candidates = [d for d in bio_domains(bio) + domains if not any(d == t or d.endswith('.' + t) for t in THIRD_PARTY)]
        cfg = gemini.settings() or {}
        external = settings is not None and getattr(settings, 'external_io_enabled', False)
        site = read_project(candidates[0] if candidates else None, cfg.get('proxy'),
                            [l for t in tweets for l in t.get('links', [])]) if external else {'site': '', 'docs': ''}
        domains = list(dict.fromkeys(candidates + domains))
        payload = {'x_handle': item['x_handle'], 'name': item['project']['name'], 'bio': bio[:2000],
                   'tweets': [t['text'] for t in tweets], 'links': domains,
                   'site': site['site'], 'docs': site['docs']}
        try:
            value = gemini.generate_json(PROMPT + json.dumps(payload, ensure_ascii=False))
        except gemini.AIUnavailable as exc:
            failures[item['discovery_id']] = now + (600 if str(exc) == 'ai_rate_limited' else 120)
            logging.getLogger(__name__).warning('hunter_ai_prefill_%s', exc)
            if str(exc) in ('ai_not_configured', 'ai_key_rejected', 'ai_network'):
                break
            continue
        store.set_state(PREFIX + item['discovery_id'], clean(value, item['x_handle'], bio, domains))
        failures.pop(item['discovery_id'], None)
        stored += 1
    # Drop suggestions whose discovery no longer exists (72h retention).
    with store.connect(True) as db:
        db.execute("DELETE FROM state WHERE key LIKE 'ai:%' AND substr(key,4) NOT IN (SELECT discovery_id FROM discoveries)")
    return stored
