import hashlib
import time

import pytest

from hunterradar.parsers import Follow, Target
from hunterradar.store import Store

NOW = time.time()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path.resolve()/'hunter.db')


def ready(store, username='hunter1', followers=5000, user_id=None, now=NOW):
    row = store.add(username, now=now-300000)
    store.apply_profile(row, user_id or str(100+len(store.hunters())), username, followers, now)
    return store.hunter(row['id'])


def event(username='hunter1', target='project1', at=NOW, key=None, target_id='999', received=NOW):
    key = key or hashlib.sha256(f'{username}:{target}:{at}'.encode()).hexdigest()
    return Follow(username, Target(target, target_id, 'Project One', 'Evidence bio'), at, received, '6551_WSS', key)


def discover(store, now=NOW):
    for i in (1,2):
        ready(store, 'hunter'+str(i), user_id=str(100+i), now=now)
        store.ingest_wss(event('hunter'+str(i),at=now,received=now))
    return store.discovery('project1')


def reviewed(store, now=NOW):
    item = discover(store, now)
    return store.review('project1', item['version'], {'name':'Project One','description':'reviewed',
                        'website':'https://example.org','notes':'human reviewed','rating':'A'},'admin', now)
