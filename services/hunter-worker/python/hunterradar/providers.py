from __future__ import annotations

import time
import hashlib
from email.utils import parsedate_to_datetime

import httpx

from .config import Settings
from .store import Store


class ProviderError(Exception):
    def __init__(self, code, retry_after=0):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)


class Providers:
    """All provider routes are explicitly read-only. Never reconcile shared Watch."""
    def __init__(self, settings: Settings, store: Store, client: httpx.AsyncClient | None = None):
        self.settings, self.store = settings, store
        self.client = client or httpx.AsyncClient(timeout=settings.timeout, follow_redirects=False, trust_env=False)
        self.owns_client = client is None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

    async def request(self, operation, username=None):
        if not self.settings.external_io_enabled:
            raise ProviderError('external_io_disabled', 300)
        now = time.time()
        if operation == 'followings':
            if not self.settings.token_twitterapi:
                raise ProviderError('twitterapi_key_missing', 300)
            provider, cost, limit = 'twitterapi', 60, self.settings.daily_twitterapi
            method, url = 'GET', 'https://api.twitterapi.io/twitter/user/followings'
            kwargs = {'params': {'userName': username, 'cursor': '', 'pageSize': 20},
                      'headers': {'X-API-Key': self.settings.token_twitterapi}}
        elif operation in ('profile', 'watch'):
            if not self.settings.token_6551:
                raise ProviderError('6551_token_missing', 300)
            provider, cost, limit = '6551', 1, self.settings.daily_6551
            method = 'POST'
            url = 'https://ai.6551.io/open/' + ('twitter_user_info' if operation == 'profile' else 'twitter_watch')
            kwargs = {'json': {'username': username} if operation == 'profile' else {},
                      'headers': {'Authorization': 'Bearer '+self.settings.token_6551}}
        else:
            raise ValueError('unapproved_provider_operation')
        cooldown = self.store.states().get('cooldown:'+provider, 0)
        if cooldown > now:
            raise ProviderError('provider_cooldown', cooldown-now)
        intent='provider_intent:'+operation+':'+hashlib.sha256((username or '').encode()).hexdigest()
        if self.store.states().get(intent) in ('in_flight','billing_unknown'):
            raise ProviderError('provider_billing_unknown',9999999999-now)
        # Every attempt, including failed/ambiguous requests, reserves budget before IO.
        self.store.reserve(provider, cost, limit, self.settings.requests_per_minute, now)
        self.store.set_state(intent,'in_flight')
        try:
            response = await self.client.request(method, url, **kwargs)
            self.store.set_state(intent,None)
            if response.status_code == 429:
                try:
                    wait = min(86400, max(60, int(response.headers.get('retry-after', '60'))))
                except ValueError:
                    try:wait=min(86400,max(60,parsedate_to_datetime(response.headers['retry-after']).timestamp()-now))
                    except (ValueError,TypeError,KeyError,OverflowError):wait=60
                self.store.set_state('cooldown:'+provider, now+wait)
                raise ProviderError('provider_rate_limited', wait)
            if response.status_code in (401, 403):
                self.store.set_state('cooldown:'+provider, now+3600)
                raise ProviderError('provider_auth_failed', 3600)
            if response.status_code != 200:
                raise ProviderError('provider_http_'+str(response.status_code), 60)
            if len(response.content) > 2_000_000:
                raise ProviderError('provider_response_too_large', 300)
            payload = response.json()
            if not isinstance(payload, dict) or payload.get('success') is False or payload.get('status') == 'error':
                raise ProviderError('provider_application_error', 300)
            return payload
        except (httpx.ReadTimeout,httpx.WriteTimeout,httpx.ReadError,httpx.WriteError,httpx.RemoteProtocolError):
            self.store.set_state(intent,'billing_unknown')
            raise ProviderError('provider_billing_unknown',9999999999-time.time()) from None
        except (httpx.HTTPError, ValueError):
            self.store.set_state(intent,None)
            # Do not log exceptions containing URLs, token query strings or provider bodies.
            raise ProviderError('provider_transport_or_json_error', 30) from None
