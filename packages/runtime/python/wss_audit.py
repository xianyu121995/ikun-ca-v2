"""Allowlisted WSS diagnostics only. Logging failure must never change event processing."""
from contextlib import asynccontextmanager
import asyncio
import json
import logging
import re
import time
import uuid

LOGGER = logging.getLogger('ikun.wss.receive')
LOGGER.setLevel(logging.INFO)
EVENTS = frozenset(('NEW_TWEET','NEW_TWEET_QUOTE','NEW_TWEET_REPLY','NEW_RETWEET',
    'NEW_FOLLOWER','NEW_UNFOLLOWER','NEW_ARTICLE','ARTICLE','CA','CA_CREATE',
    'UPDATE_NAME','UPDATE_DESCRIPTION','UPDATE_AVATAR','UPDATE_BANNER',
    'TWEET_TOPPING','DELETE','SYSTEM','TRANSLATE'))


def note(callback, reason):
    if callback is not None:
        try:callback(reason)
        except Exception:pass


def metadata(message):
    params = message.get('params') if isinstance(message,dict) else None
    params = params if isinstance(params,dict) else {}
    kind = params.get('eventType')
    account = params.get('twAccount')
    account = account.lower().removeprefix('@') if isinstance(account,str) else ''
    if not re.fullmatch(r'[a-z0-9_]{1,15}',account):account = None
    content = params.get('content')
    if isinstance(content,str):
        try:content = json.loads(content)
        except (ValueError,TypeError):content = None
    identifier = content.get('id',content.get('id_str')) if isinstance(content,dict) else None
    identifier = str(identifier) if type(identifier) in (str,int) else ''
    if not re.fullmatch(r'[0-9]{1,40}',identifier):identifier = None
    event_id = params.get('id')
    event_id = str(event_id) if type(event_id) in (str,int) else ''
    if not re.fullmatch(r'[0-9]{1,40}',event_id):event_id = None
    return {'event_type':kind if isinstance(kind,str) and kind in EVENTS else 'unknown',
            'account':account,'tweet_id':identifier,'provider_event_id':event_id}


class FrameAudit:
    def __init__(self,audit,fields):self.audit,self.fields = audit,fields
    def drop(self,reason):self.audit.emit('dropped',self.fields,reason)
    def accepted(self):self.audit.emit('accepted',self.fields,'stored_or_enriched')


class WssAudit:
    def __init__(self,engine):
        if engine not in ('hunter','tracking'):raise ValueError('invalid_audit_engine')
        self.engine,self.connection = engine,str(uuid.uuid4())
        self.last_pong = float('-inf')

    def emit(self,action,fields=None,reason=None):
        try:
            data = {'audit':'wss-receive-v1','at':time.time(),'engine':self.engine,
                    'connection':self.connection,'action':action}
            if fields:data.update(fields)
            if reason:data['reason'] = reason
            LOGGER.info(json.dumps(data,separators=(',',':'),ensure_ascii=True))
        except Exception:pass

    def frame(self,message):
        try:fields = metadata(message)
        except Exception:fields = {'event_type':'unknown','account':None,'tweet_id':None,'provider_event_id':None}
        self.emit('received',fields)
        return FrameAudit(self,fields)

    def pong(self):
        now = time.monotonic()
        if now-self.last_pong >= 60:
            self.last_pong = now
            self.emit('heartbeat',reason='application_pong')


@asynccontextmanager
async def connection(manager,engine):
    audit = WssAudit(engine)
    audit.emit('connecting')
    try:
        async with manager as socket:
            audit.emit('connected')
            yield socket,audit
    except BaseException as error:
        if isinstance(error,asyncio.CancelledError):reason = 'cancelled'
        elif isinstance(error,TimeoutError):reason = 'timeout'
        else:reason = 'connection_or_processing_error'
        audit.emit('disconnected',reason=reason)
        raise
    else:audit.emit('closed',reason='normal_return')
