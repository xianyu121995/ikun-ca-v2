from __future__ import annotations

import hashlib
import json
import re
import math
from dataclasses import dataclass
from datetime import datetime


def handle(value) -> str:
    value = str(value or '').strip().removeprefix('@').lower()
    if not re.fullmatch(r'[a-z0-9_]{1,15}', value):
        raise ValueError('invalid_x_handle')
    return value


def timestamp(value) -> float:
    if isinstance(value, (int, float)):
        if isinstance(value,bool) or not math.isfinite(value) or value<0:raise ValueError('invalid_event_time')
        return float(value) / (1000 if value > 1e12 else 1)
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timezone_required')
    return dt.timestamp()


def follower_count(data) -> int | None:
    """Follower count already present on a user object. Missing or invalid stays None.

    twitterapi.io followings (UserProfileSnake) includes followers_count. WSS
    content sometimes does not. This never triggers a request.
    """
    if not isinstance(data, dict):
        return None
    for key in ('followers_count', 'followersCount', 'followerCount', 'followers', 'follower_count'):
        if key not in data:
            continue
        value = data[key]
        if type(value) is int and value >= 0:
            return value
    return None


@dataclass(frozen=True)
class Target:
    username: str
    user_id: str | None = None
    name: str = ''
    description: str = ''
    followers: int | None = None


@dataclass(frozen=True)
class Follow:
    hunter: str
    target: Target
    occurred_at: float
    received_at: float
    source: str
    key: str
    time_basis: str = 'provider_event'


def wss_events(payload: dict, received_at: float) -> list[Follow]:
    if payload.get('method') != 'twitter.event':
        return []
    params = payload.get('params', {})
    if not isinstance(params, dict) or params.get('eventType') != 'NEW_FOLLOWER':
        return []
    hunter = handle(params.get('twAccount'))
    # Outer timestamp is the follow event timestamp. Profile createdAt is NOT follow time.
    event_time = timestamp(params.get('createdAt'))
    if event_time < received_at - 72 * 3600 or event_time > received_at + 60:
        raise ValueError('stale_or_future_event')
    content = params.get('content')
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, list):
        raise ValueError('follow_content_must_be_array')
    result = []
    for item in content:
        if not isinstance(item, dict):
            raise ValueError('invalid_follow_target')
        if item.get('twId') is not None and (isinstance(item['twId'],bool) or not re.fullmatch(r'[0-9]{1,40}',str(item['twId']))):
            raise ValueError('invalid_target_stable_id')
        target = Target(handle(item.get('twAccount')), str(item['twId']) if item.get('twId') else None,
                        str(item.get('twUserName') or '')[:200], str(item.get('description') or '')[:10000],
                        follower_count(item))
        if hunter == target.username:
            continue
        # Include target even when one envelope id contains many targets.
        identity = [hunter, target.username, params.get('id'), event_time]
        key = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
        result.append(Follow(hunter, target, event_time, received_at, '6551_WSS', key))
    return result


def profile(payload: dict, expected: str) -> tuple[str, str, int]:
    data = payload.get('data')
    if not isinstance(data, dict):
        raise ValueError('profile_missing_data')
    account = data.get('screenName') or data.get('twAccount') or data.get('userName')
    if account and handle(account) != expected:
        raise ValueError('profile_identity_mismatch')
    count = next((data[k] for k in ('followersCount', 'followerCount', 'followers', 'follower_count') if k in data), None)
    user_id = next((data[k] for k in ('twId', 'userId', 'idStr', 'twitterId', 'id') if data.get(k)), None)
    if isinstance(count, bool) or not str(count).isdigit() or not re.fullmatch(r'[0-9]{1,40}',str(user_id)):
        raise ValueError('profile_missing_stable_id_or_follower_count')
    return str(user_id), str(data.get('name') or data.get('twUserName') or expected)[:200], int(count)


def followings(payload: dict) -> list[Target]:
    rows = payload.get('followings')
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValueError('invalid_followings_page')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r'[0-9]{1,40}',str(row.get('id'))) or row.get('unavailable'):
            raise ValueError('invalid_following_identity')
        name = handle(row.get('userName'))
        if name not in seen:
            result.append(Target(name, str(row['id']), str(row.get('name') or name)[:200], str(row.get('description') or '')[:10000], follower_count(row)))
            seen.add(name)
    return result


def watch_coverage(payload: dict) -> set[str]:
    data = payload.get('data')
    if not isinstance(data, list):
        raise ValueError('unsupported_watch_response')
    covered = set()
    for row in data:
        if isinstance(row, dict) and row.get('newFlwBol') is True:
            try:
                covered.add(handle(row.get('twAccount') or row.get('username')))
            except ValueError:
                continue
    return covered
