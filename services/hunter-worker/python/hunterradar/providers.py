from __future__ import annotations

import time
import json
import hashlib
from email.utils import parsedate_to_datetime

import httpx

from .config import Settings
from .store import Store


class ProviderError(Exception):
    def __init__(self, code, retry_after=0, *, retryable=True):
        self.code, self.retry_after, self.retryable = code, retry_after, retryable
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

    async def watch_write(self, endpoint, body):
        if not self.settings.external_io_enabled or endpoint not in ('twitter_watch_add','twitter_watch_delete'):
            raise ProviderError('external_io_disabled')
        self.store.reserve('6551',1,self.settings.daily_6551,self.settings.requests_per_minute,time.time())
        try:
            response=await self.client.post('https://ai.6551.io/open/'+endpoint,json=body,headers={'Authorization':'Bearer '+self.settings.token_6551})
            if response.status_code!=200 or response.json().get('success') is not True:
                raise ProviderError('watch_mutation_failed',60)
        except (httpx.HTTPError,ValueError):
            raise ProviderError('watch_mutation_uncertain',30) from None

    async def request(self, operation, username=None):
        if not self.settings.external_io_enabled:
            raise ProviderError('external_io_disabled', 300)
        return await self._read_only(operation, username)

    async def _read_only(self, operation, username=None, *, sample_permit=None):
        """Shared transport; formal request keeps its hard gate above.

        With formal IO closed, even this private helper requires the exact
        reviewed Permit and reserves one bounded operation before transport.
        """
        if not self.settings.external_io_enabled:
            from .sample_only import Permit
            if (type(sample_permit) is not Permit or not self.settings.require_external_io_disabled or not self.settings.v2_mode
                    or sample_permit.store.path!=self.store.path):
                raise ProviderError('external_io_disabled', 300)
            sample_permit.claim(operation, username)
        now = time.time()
        if operation == 'followings':
            if not self.settings.token_twitterapi:
                raise ProviderError('twitterapi_key_missing', 300)
            provider, cost, limit = 'twitterapi', 60, self.settings.daily_twitterapi
            method, url = 'GET', 'https://api.twitterapi.io/twitter/user/followings'
            kwargs = {'params': {'userName': username, 'cursor': '', 'pageSize': 20},
                      'headers': {'X-API-Key': self.settings.token_twitterapi},
                      'timeout': httpx.Timeout(max(60, self.settings.timeout), connect=self.settings.timeout, pool=self.settings.timeout)}
        elif operation in ('profile', 'watch'):
            if not self.settings.token_6551:
                raise ProviderError('6551_token_missing', 300)
            provider, cost, limit = '6551', 1, self.settings.daily_6551
            method = 'POST'
            url = 'https://ai.6551.io/open/' + ('twitter_user_info' if operation == 'profile' else 'twitter_watch')
            kwargs = {'json': {'username': username} if operation == 'profile' else {},
                      'headers': {'Authorization': 'Bearer '+self.settings.token_6551}}
            if operation == 'watch':
                # Listing all shared Watches can take longer; writes/profile calls keep their existing timeout.
                kwargs['timeout'] = httpx.Timeout(self.settings.timeout, read=max(20, self.settings.timeout))
        else:
            raise ValueError('unapproved_provider_operation')
        states = self.store.states()
        result_key = 'provider_result:'+operation+':'+hashlib.sha256((username or '').encode()).hexdigest()
        pending = states.get(result_key) if operation == 'followings' else None
        generation = None
        if operation == 'followings':
            with self.store.connect() as db:
                account = db.execute('SELECT id,generation FROM hunters WHERE username=?',(username,)).fetchone()
                generation = [account['id'],account['generation']] if account else None
        if pending:
            if pending.get('generation') != generation or now-pending['received_at'] > 3600:
                raise ProviderError('provider_result_requires_reconciliation',9999999999-now)
            return pending['payload']
        blocked = self.store.provider_block(operation, username, states=states)
        if blocked:
            raise ProviderError(blocked['code'], retryable=False)
        cooldown = states.get('cooldown:'+provider, 0)
        if cooldown > now:
            raise ProviderError('provider_cooldown', cooldown-now)
        intent='provider_intent:'+operation+':'+hashlib.sha256((username or '').encode()).hexdigest()
        if states.get(intent) in ('in_flight','billing_unknown'):
            raise ProviderError('provider_billing_unknown',9999999999-now)
        # Every attempt, including failed/ambiguous requests, reserves budget before IO.
        self.store.reserve(provider, cost, limit, self.settings.requests_per_minute, now)
        self.store.set_state(intent,'in_flight')
        started = time.monotonic()
        try:
            response = await self.client.request(method, url, **kwargs)
            if (provider == 'twitterapi' and response.status_code == 402) or response.status_code in (400, 404):
                code = 'provider_http_'+str(response.status_code)
                # Keep in_flight until the durable terminal block is committed.
                # A crash before that commit therefore still forbids blind replay.
                self.store.block_provider(operation, username, code, intent,
                                          provider_wide=response.status_code == 402, now=now)
                raise ProviderError(code, retryable=False)
            if response.status_code == 200 and operation == 'followings':
                pass  # Keep the billing fence until the successful payload is durable.
            else:
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
            if operation == 'followings':
                with self.store.connect(True) as db:
                    for key, value in ((result_key, {'payload':payload,'received_at':time.time(),'generation':generation}),(intent,None)):
                        db.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))
            return payload
        except (httpx.ReadTimeout,httpx.WriteTimeout,httpx.ReadError,httpx.WriteError,httpx.RemoteProtocolError) as error:
            self.store.set_state('provider_failure:'+operation+':'+hashlib.sha256((username or '').encode()).hexdigest(), {'kind':type(error).__name__,'elapsed_seconds':round(time.monotonic()-started,3),'at':time.time()})
            self.store.set_state(intent,'billing_unknown')
            raise ProviderError('provider_billing_unknown',9999999999-time.time()) from None
        except (httpx.HTTPError, ValueError) as error:
            if operation == 'followings' and isinstance(error, ValueError):
                self.store.set_state(intent,'billing_unknown')
                raise ProviderError('provider_billing_unknown',9999999999-time.time()) from None
            self.store.set_state(intent,None)
            # Do not log exceptions containing URLs, token query strings or provider bodies.
            raise ProviderError('provider_transport_or_json_error', 30) from None
