"""Own only the exact marked Watch created by this hunter; never rewrite shared rows."""
import time
from .providers import ProviderError

FLAGS = ('newTweetBol','newFlwBol','newUnFlwBol','newTweetReplyBol','newTweetQuoteBol','newRetweetBol','updateNameBol','updateDescBol','updateAvatarBol','updateBannerBol','newCaBol','tweetToppingBol')

def rows(payload):
    data = payload.get('data')
    if isinstance(data, dict):
        items = data.get('list', data.get('items'))
        if not isinstance(items, list) or data.get('total', len(items)) != len(items):
            raise ProviderError('incomplete_watch_snapshot')
    else:
        items = data
    if not isinstance(items, list):
        raise ProviderError('invalid_watch_snapshot')
    result = {}
    for item in items:
        if not isinstance(item, dict):raise ProviderError('invalid_watch_snapshot')
        name = str(item.get('twAccount', item.get('username', ''))).lower().removeprefix('@')
        if not name or name in result:raise ProviderError('invalid_watch_snapshot')
        result[name] = item
    return result

async def synchronize(engine):
    from watch_lock import watch_lock
    async with watch_lock(engine.store.path):
        snapshot = rows(await engine.providers.request('watch'))
        errors = []
        for row in engine.store.hunters(include_deleted=True):
            try:
                wanted = not row['deleted_at'] and row['enabled'] and row['mode']=='WSS' and row['profile_status']=='ready'
                marker = 'ikun-ca-v2:hunter:' + row['id']
                key = 'owned_watch:' + row['id']
                saved = engine.store.states().get(key)
                watch = snapshot.get(row['username'])
                blocked_key = 'watch_blocked:'+row['id']
                blocked = engine.store.states().get(blocked_key)
                if wanted and blocked and (not watch or watch.get('newFlwBol') is not True):
                    errors.append(blocked);continue
                if wanted and blocked:engine.store.set_state(blocked_key,None)
                owned = bool(saved and watch and watch.get('remark')==marker and (saved.get('id') is None or str(watch.get('id'))==saved['id']))
                if wanted and not watch:
                    if len(snapshot) >= 600:
                        errors.append('quota_exhausted');continue
                    engine.store.set_state(key, {'id':None,'marker':marker})
                    await engine.providers.watch_write('twitter_watch_add', {'username':row['username'],'groupName':'ikun-ca-v2-hunters','remark':marker,**{f:f=='newFlwBol' for f in FLAGS}})
                    snapshot = rows(await engine.providers.request('watch'))
                    watch = snapshot.get(row['username'])
                    if not watch or watch.get('remark')!=marker or watch.get('newFlwBol') is not True:
                        errors.append('watch_verification_failed');continue
                    engine.store.set_state(key, {'id':str(watch.get('id')),'marker':marker})
                elif wanted and watch.get('newFlwBol') is not True:
                    approved = engine.store.states().get('approved_flag:'+row['id'])
                    if approved and str(watch.get('id')) == approved['id']:
                        before = dict(watch)
                        body = {'username':row['username'], 'remark':watch.get('remark',''), **{f:watch.get(f) is True for f in FLAGS}}
                        body['newFlwBol'] = True
                        engine.store.set_state(key, {'kind':'flag','id':approved['id'],'before':before})
                        await engine.providers.watch_write('twitter_watch_add', body)
                        snapshot = rows(await engine.providers.request('watch'))
                        updated = snapshot.get(row['username'],{})
                        if str(updated.get('id'))!=approved['id'] or updated.get('twGroupId')!=before.get('twGroupId') or updated.get('newFlwBol') is not True or any(updated.get(f)!=before.get(f) for f in FLAGS if f!='newFlwBol'):
                            engine.store.set_state(blocked_key,'existing_watch_update_unsupported')
                        raise ProviderError('existing_watch_update_unsupported',300)
                    else:
                        errors.append('existing_watch_owned_elsewhere')
                elif row['deleted_at'] and saved:
                    if not watch:
                        engine.store.set_state(key,None)
                    elif saved.get('kind')=='flag' and str(watch.get('id'))==saved['id']:
                        # Withdraw only the flag explicitly enabled by ikun, retaining every current other setting.
                        await engine.providers.watch_write('twitter_watch_add', {'username':row['username'],'remark':watch.get('remark',''),**{f:False if f=='newFlwBol' else watch.get(f) is True for f in FLAGS}})
                        snapshot = rows(await engine.providers.request('watch'))
                        if snapshot.get(row['username'],{}).get('newFlwBol') is False:engine.store.set_state(key,None)
                        else:errors.append('watch_flag_delete_not_verified')
                    elif owned and all(watch.get(f) is False for f in FLAGS if f!='newFlwBol'):
                        await engine.providers.watch_write('twitter_watch_delete', {'username':row['username']})
                        snapshot = rows(await engine.providers.request('watch'))
                        if row['username'] in snapshot:errors.append('watch_delete_not_verified')
                        else:engine.store.set_state(key,None)
                    else:errors.append('watch_delete_ownership_conflict')
            except ProviderError as error:
                if error.code=='watch_mutation_failed':engine.store.set_state('watch_blocked:'+row['id'],error.code)
                errors.append(error.code)
                snapshot = rows(await engine.providers.request('watch'))
        engine.store.coverage({name for name,w in snapshot.items() if w.get('newFlwBol') is True},time.time())
        engine.store.set_state('watch_error', ','.join(sorted(set(errors))) or None)
        engine.store.set_state('watch_slots', {'used':len(snapshot),'capacity':600})
