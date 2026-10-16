"""One owner-approved bounded retry; never silently turns into an automatic retry loop."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time
from v2_maintenance import V2,backup
from upgrade_v2_workers import unload,launch,DOMAIN

KEY='owner-approved-rest-retry-20261017-1'

async def attempt(store,settings):
    from hunterradar.providers import Providers,ProviderError
    from hunterradar.parsers import followings
    rows=[r for r in store.hunters() if r['enabled'] and r['mode']=='REST' and r['poll_error']=='provider_billing_unknown']
    if len(rows)!=1:raise RuntimeError('expected_one_blocked_rest_account')
    row=rows[0]
    if store.states().get(KEY):raise RuntimeError('approved_retry_already_consumed')
    intent='provider_intent:followings:'+hashlib.sha256(row['username'].encode()).hexdigest()
    before=store.states().get(intent)
    assert before in ('billing_unknown','in_flight')
    store.set_state(KEY,{'account_id':row['id'],'state':'reserved','prior_intent':before,'at':time.time()})
    store.set_state(intent,None)
    provider=Providers(settings,store)
    try:
        payload=await provider.request('followings',row['username'])
        result=store.apply_poll(row,followings(payload),time.time())
        store.set_state(KEY,{'account_id':row['id'],'state':'succeeded','baseline':bool(result.get('baseline')),'at':time.time()})
        print('One REST retry succeeded; normal hourly schedule restored',flush=True)
    except Exception as error:
        code=error.code if isinstance(error,ProviderError) else type(error).__name__
        # The original error remains visible. No automatic second attempt is scheduled.
        store.job_failure(row,'poll','owner_approved_retry_failed:'+code,9999999999)
        store.set_state(KEY,{'account_id':row['id'],'state':'failed','error_code':code,'at':time.time()})
        print('One REST retry failed; alert retained:',code,flush=True)
    finally:await provider.close()

def main():
    os.umask(0o077)
    label='ca.ikun.v2.c0lite.hunter';path=Path.home()/'Library/LaunchAgents'/(label+'.plist')
    job=plistlib.loads(path.read_bytes());entry=Path(job['ProgramArguments'][1]);release=entry.parents[2]
    sys.path[:0]=[str(release/'services/hunter-worker/python'),str(release/'packages/runtime/python')]
    os.environ.update(json.loads((V2/'config/hunter.live.environment.json').read_text()))
    from hunterradar.config import Settings
    from hunterradar.store import Store
    store=Store(V2/'data/hunter/hunter.db')
    if store.states().get(KEY):raise RuntimeError('approved_retry_already_consumed')
    backup()
    unload(label)
    token=None
    try:
        for i in range(40):
            try:token=store.acquire_worker();break
            except RuntimeError:time.sleep(.5)
        if not token:raise RuntimeError('hunter_lease_not_released')
        asyncio.run(attempt(store.worker_view(token),Settings.load()))
    finally:
        if token:store.release_worker(token)
        result=launch('bootstrap',DOMAIN,path)
        if result.returncode:raise RuntimeError('hunter_restart_failed')

if __name__=='__main__':main()
