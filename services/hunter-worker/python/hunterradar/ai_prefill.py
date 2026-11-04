"""AI Chinese prefill for new Hunter discoveries.

Name, website, description, notes and category stay a draft in state 'ai:<discovery_id>' until the
owner saves. S/A/B/忽略 are written onto discoveries.rating immediately so the list can show them.
忽略 is only a prefill: it does not set ignored, so the row stays in the default list. A person
hiding a row is the only path that sets ignored=1. A rating a person already saved is left alone.
The one-sentence reason is stored on the suggestion and on discoveries.rating_reason.

signal_count (distinct hunters) is always passed in. followers_count is included only when a
followings or WSS user object the collector already received carried one
(UserProfileSnake.followers_count, or the same keys on a WSS content item). Nothing calls a
profile endpoint just to count followers. When that field was absent, the prompt omits it.
"""
from __future__ import annotations

import json
import logging
import os
from provider_6551 import configured, Blocked, quota_response, response_error
import re
import time
from urllib.parse import urlsplit

import httpx

from . import gemini

PREFIX = 'ai:'
# Isolated rating rubric. Replace this constant alone when the wording changes.
# Do not restate S/A/B/忽略 elsewhere. Owner clarification 2026-11-05: ecosystem
# duplicates (including Elysium) and a future start date are not ignore reasons.
RATING_RUBRIC = (
    "- rating：只能是 S、A、B、忽略 四个字面量之一，不要输出别的等级。只判断这个新项目现在有没有机会参与。材料没写的不要编造。\n"
    "  S（重点跟）：同时满足 ①机制清楚（怎么发币/mint/挖）②有代币或明确发行计划（$TICKER、TGE、预售、公平发射）③参与入口已开放或时间已定。开始日期在未来，但机制和代币都清楚的，仍是 S，不要因为还要等几天就降成忽略。新发射台和新发行机制（Agent 门槛 mint、PoW、新 bonding curve 玩法）优先。有官网/文档、被官方大号关注、≥5 个猎手同时关注、粉丝多是加分项。\n"
    "  A（持续跟踪）：有明确参与路径但未开始或细节不全（waitlist、白名单、Genesis Pass、积分、测试网）；已表明有代币/要发币；NFT+代币的链游或应用；新链上有产品描述的早期发射台或协议。参与时间已定但还没开始（例如写了未来日期）归 A；机制和代币都清楚时升为 S。\n"
    "  B（先记着）：是项目但暂无可参与的东西：没代币没玩法的纯 NFT 免费mint/白名单；除此之外没有内容的纯 PFP/艺术 NFT；一句话的 DEX/发射台；只有 coming soon；等 CA/等代币。信息少但确实是项目的归 B。纯 PFP 归 B，不归忽略。\n"
    "  忽略（仅预填）：只限个人号（创始人/CM/大使/KOL/艺术家）、与加密无关、简介为空或只有口号且没有官网佐证、已经结束无法参与、明显广告或喊单。所在生态项目多、同质、或属于 Elysium/Hyperliquid，都不是忽略理由。未来才开始也不是忽略。\n"
    "  热度（猎手数 signal_count、粉丝数 followers_count）只作加分项，不单独决定档位。\n"
)
PROMPT = (
    "你是加密货币/Web3 项目研究助手。根据下面 X 账号的名称和简介，用简体中文帮我预填项目资料。要求：\n"
    "资料包括：账号名称、简介、最近几条推文（tweets）、推文里出现过的外部链接（links），以及官网首页文字（site）和官网文档/白皮书页文字（docs，如有）。优先依据官网和文档判断项目具体做什么。\n"
    "- name：一句很短的中文项目名，概括它是做什么的、在哪条链上，风格例如“SOL上的AI审计发射台”“HYP高性能L2”“RWA农业游戏”，不超过 16 个字；看不出来就用原名。\n"
    "- website：从简介或 links 里挑出项目自己的官网域名（如 pindar.finance），不要选 x.com、t.co、linktr.ee、discord、telegram、github、medium 这类第三方站点，没有就给空字符串，不要编造。\n"
    "- description：两到三句中文简介，说明项目具体做什么（产品/机制/所在链）、进展到哪（如测试网/主网），依据官网文档、简介和推文，不要编造。\n"
    "- notes：一句中文备注，点出值得关注的信号（如代币、白名单、测试网、空投、NFT、即将上线），没有就给空字符串。\n"
    "- category：项目类型，只能从 NFT、发射台、新协议、撸毛、链游 五个里选一个最贴切的（链游=区块链游戏/GameFi；撸毛=主要玩法是做任务/交互/测试网拿空投积分；发射台=帮别人发币/发项目的平台；NFT=以 NFT 为核心；新协议=其他新的链上协议/产品/基础设施），实在判断不了给空字符串。\n"
    + RATING_RUBRIC +
    "- rating_reason：一句简体中文，不超过 40 个字，只解释这个评级，不要换行。\n"
    "signal_count 是有多少位不同猎手关注了这个账号。followers_count 只有在已收到的关注列表资料里带了粉丝数时才会出现；没有这个字段就不要编造粉丝数。\n"
    "只输出 JSON：{\"name\": ..., \"website\": ..., \"description\": ..., \"notes\": ..., \"category\": ..., \"rating\": \"S\"|\"A\"|\"B\"|\"忽略\", \"rating_reason\": ...}\n\n"
)
PROJECT_TYPES = ('NFT', '发射台', '新协议', '撸毛', '链游')
RATINGS = ('S', 'A', 'B', '忽略')
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


def rest_input(settings, store, operation, handle):
    """AI runs in a worker thread; reuse the same TWI budget and billing fences."""
    if store is None or not settings.external_io_enabled:return None
    import asyncio
    from .providers import Providers, ProviderError
    from .store import BudgetExceeded
    async def read():
        provider = Providers(settings, store)
        try:return await provider.request(operation, handle)
        finally:await provider.close()
    try:return asyncio.run(read())
    except (ProviderError, BudgetExceeded, ValueError):return None


def recent_tweets(settings, handle, limit=8, *, store=None):
    """Read-only 6551 lookup of a discovery's latest tweets (text + expanded links). Failures return []."""
    if getattr(settings, 'rest_only', False):
        payload = rest_input(settings, store, 'tweets', handle) or {}
        data = payload.get('data') or {}
        tweets = data.get('tweets') if isinstance(data,dict) else None
        out = []
        for tweet in tweets if isinstance(tweets,list) else []:
            if not isinstance(tweet,dict) or not isinstance(tweet.get('text'),str):continue
            entities = tweet.get('entities') or {}
            links = [u.get('expanded_url') or u.get('url') for u in entities.get('urls',[])
                     if isinstance(u,dict) and isinstance(u.get('expanded_url') or u.get('url'),str)]
            out.append({'text':tweet['text'][:600], 'links':links[:5]})
        return out[:limit]
    if os.environ.get('IKUN_6551_REST_PAUSED') == '1' or settings is None or not getattr(settings, 'external_io_enabled', False) or not getattr(settings, 'token_6551', ''):
        return []
    ledger=configured();permit=None
    try:
        if ledger:permit=ledger.begin('hunter_ai','twitter_user_tweets',purpose='ai_input')
        with httpx.Client(timeout=15) as client:
            response = client.post('https://ai.6551.io/open/twitter_user_tweets',
                                   json={'username': handle, 'maxResults': limit, 'product': 'Latest',
                                         'includeReplies': False, 'includeRetweets': False},
                                   headers={'Authorization': 'Bearer ' + settings.token_6551})
        quota=quota_response(response)
        if ledger:ledger.finish(permit,response.status_code,quota=quota,error=response_error(response));permit=None
        data = response.json().get('data') if response.status_code == 200 else None
    except Blocked:return []
    except (httpx.HTTPError, ValueError) as e:
        if ledger and permit:ledger.finish(permit,error=type(e).__name__)
        return []
    out = []
    for t in data if isinstance(data, list) else []:
        if not isinstance(t, dict) or not isinstance(t.get('text'), str):
            continue
        links = [u.get('url') for u in t.get('urls') or [] if isinstance(u, dict) and isinstance(u.get('url'), str)]
        out.append({'text': t['text'][:600], 'links': links[:5]})
    return out[:limit]


def profile_website(settings, handle, *, store=None):
    """The website field of the X profile (twitterapi.io user/info entities.url). Read-only; failures return None."""
    token = getattr(settings, 'token_twitterapi', '') if settings is not None else ''
    if not token or not getattr(settings, 'external_io_enabled', False):
        return None
    try:
        if getattr(settings, 'rest_only', False):
            data = (rest_input(settings,store,'ai_profile',handle) or {}).get('data')
        else:
            with httpx.Client(timeout=15) as client:
                response = client.get('https://api.twitterapi.io/twitter/user/info', params={'userName': handle},
                                      headers={'X-API-Key': token})
            data = response.json().get('data') if response.status_code == 200 else None
        urls = (((data or {}).get('entities') or {}).get('url') or {}).get('urls') or []
        for item in urls:
            host = (urlsplit(item.get('expanded_url') or '').hostname or '').lower().removeprefix('www.')
            if host and not any(host == d or host.endswith('.' + d) for d in THIRD_PARTY):
                return host
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        return None
    return None


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
    reason = ' '.join(text('rating_reason', 80).split())
    rating = text('rating', 8)
    out = {'name': text('name', 60) or handle, 'website': website, 'description': text('description', 600),
           'notes': text('notes', 300), 'category': text('category', 10) if text('category', 10) in PROJECT_TYPES else '',
           'generated_at': time.time()}
    if rating in RATINGS and reason:
        out['rating'] = rating
        out['rating_reason'] = reason[:40]
    return out


def _count(value):
    return value if type(value) is int and value >= 0 else None


def prompt_input(item, bio, tweets, domains, site) -> dict:
    """Facts sent to the model. followers_count is omitted unless already known."""
    payload = {'x_handle': item['x_handle'], 'name': item['project']['name'], 'bio': bio[:2000],
               'tweets': [t['text'] for t in tweets], 'links': domains,
               'site': site['site'], 'docs': site['docs'],
               'signal_count': _count(item.get('signal_count'))}
    followers = _count(item.get('followers'))
    if followers is None:
        followers = _count(item.get('followers_count'))
    if followers is not None:
        payload['followers_count'] = followers
    return payload


def apply_rating(store, item, suggestion) -> None:
    """Write S/A/B/忽略 onto discoveries.rating. Never sets ignored. Skip a human rating."""
    rating = suggestion.get('rating')
    if rating not in RATINGS:
        return
    reason = suggestion.get('rating_reason')
    reason = ' '.join(reason.split())[:40] if isinstance(reason, str) else ''
    from .migration import ensure_rating_reason
    ensure_rating_reason(store.path)
    with store.connect(True) as db:
        row = db.execute('SELECT * FROM discoveries WHERE discovery_id=?', (item['discovery_id'],)).fetchone()
        if row is None:
            return
        human = bool(row['project_json']) or bool((row['name'] or '').strip()) or bool(row['ignored']) or row['rating'] in ('S', 'A', 'B', 'C', 'D')
        if human:
            logging.getLogger(__name__).info('hunter_ai_rating_kept discovery=%s', item['discovery_id'])
            return
        now = time.time()
        changed = db.execute(
            '''UPDATE discoveries SET rating=?, rating_reason=?, version=version+1, updated_at=?
               WHERE discovery_id=? AND version=? AND ignored=0
               AND rating NOT IN ('S','A','B','C','D')''',
            (rating, reason, now, item['discovery_id'], row['version'])).rowcount
        if changed:
            store.change(db, row['target'], now)


def run_pass(store, failures: dict, limit=3, settings=None) -> int:
    ledger=None if getattr(settings,'rest_only',False) else configured()
    if ledger:
        status=ledger.summary()
        if status['quota_exhausted'] or status['daily_limit_reached']:return 0
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
        cache_key = 'ai_input:' + item['x_handle']
        cached = store.get_state(cache_key)
        if cached and now - cached.get('at', 0) < 3600:
            tweets = cached.get('tweets', [])
            profile_site = cached.get('profile')
        else:
            # Fence the attempt before paid IO; a crash cannot trigger immediate replay.
            store.set_state(cache_key, {'at': now, 'tweets': []})
            kwargs = {'store':store} if getattr(settings,'rest_only',False) else {}
            tweets = recent_tweets(settings, item['x_handle'], **kwargs)
            profile_site = profile_website(settings, item['x_handle'], **kwargs)
            store.set_state(cache_key, {'at': now, 'tweets': tweets, 'profile': profile_site})
        domains = link_domains(tweets)
        from .site_reader import bio_domains, read_project
        candidates = [d for d in ([profile_site] if profile_site else []) + bio_domains(bio) + domains if not any(d == t or d.endswith('.' + t) for t in THIRD_PARTY)]
        cfg = gemini.settings() or {}
        external = settings is not None and getattr(settings, 'external_io_enabled', False)
        site = read_project(candidates[0] if candidates else None, cfg.get('proxy'),
                            [l for t in tweets for l in t.get('links', [])]) if external else {'site': '', 'docs': ''}
        logging.getLogger(__name__).info('hunter_ai_sources handle=%s site_chars=%d docs_chars=%d', item['x_handle'], len(site['site']), len(site['docs']))
        domains = list(dict.fromkeys(candidates + domains))
        payload = prompt_input(item, bio, tweets, domains, site)
        try:
            value = gemini.generate_json(PROMPT + json.dumps(payload, ensure_ascii=False))
        except gemini.AIUnavailable as exc:
            failures[item['discovery_id']] = now + (600 if str(exc) == 'ai_rate_limited' else 120)
            logging.getLogger(__name__).warning('hunter_ai_prefill_%s', exc)
            if str(exc) in ('ai_not_configured', 'ai_key_rejected', 'ai_network', 'ai_rate_limited', 'ai_codex_missing'):
                break
            continue
        suggestion = clean(value, item['x_handle'], bio, domains)
        store.set_state(PREFIX + item['discovery_id'], suggestion)
        apply_rating(store, item, suggestion)
        failures.pop(item['discovery_id'], None)
        stored += 1
    # Drop suggestions whose discovery no longer exists (72h retention).
    with store.connect(True) as db:
        db.execute("DELETE FROM state WHERE key LIKE 'ai:%' AND substr(key,4) NOT IN (SELECT discovery_id FROM discoveries)")
    return stored
