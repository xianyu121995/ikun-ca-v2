"""Persistent hourly cohorts: only the current five-minute slot, never catch-up IO.

State stays in the Hunter store; no schema or other-domain database changes.
Claims precede transport, so a crash cannot replay a possibly billed attempt.
"""
from __future__ import annotations

import copy

KEY = 'rest_batches:v1'
SLOTS = 12
SECONDS = 300


def next_slot(states, identifier, now):
    epoch = int(now//SECONDS)
    saved = states.get(KEY) or {}
    slot = next((i for i, group in enumerate(saved.get('groups',[])) if identifier in group), None)
    if slot is None:return now+3600
    return (epoch + ((slot-epoch)%SLOTS or SLOTS))*SECONDS


def claim(store, now):
    epoch = int(now // SECONDS)
    with store.transaction():
        rows = {h['id']: h for h in store.hunters() if h['enabled'] and h['profile_status'] == 'ready'}
        # Read only this key: a full states() parse inside BEGIN IMMEDIATE blocked the writer lock.
        before = store.get_state(KEY)
        saved = copy.deepcopy(before)
        if saved is None:
            # Put the remainder at the END: 85 => 7+7+...+7+8.
            ordered = sorted(rows, key=lambda k: (rows[k]['created_at'], k))
            size, extra = divmod(len(ordered), SLOTS)
            groups = [[] for _ in range(SLOTS)]
            for slot in range(SLOTS):
                count = size + (slot >= SLOTS-extra)
                groups[slot], ordered = ordered[:count], ordered[count:]
            saved = {'version':1, 'groups':groups, 'last_slot':None, 'attempts':{}}
        if saved.get('version') != 1 or len(saved['groups']) != SLOTS:
            raise ValueError('invalid_rest_batch_state')
        groups = [[k for k in group if k in rows] for group in saved['groups']]
        assigned = [k for group in groups for k in group]
        if len(set(assigned)) != len(assigned):raise ValueError('duplicate_rest_batch_member')
        for identifier in sorted(set(rows)-set(assigned)):
            smallest = min(range(SLOTS), key=lambda i:(len(groups[i]), -i))
            groups[smallest].append(identifier)
        # Membership edits move only enough accounts to restore balance.
        while max(map(len, groups))-min(map(len, groups)) > 1:
            largest = max(range(SLOTS), key=lambda i:(len(groups[i]), i))
            smallest = min(range(SLOTS), key=lambda i:(len(groups[i]), -i))
            groups[smallest].append(groups[largest].pop())
        saved['groups'] = groups
        saved['attempts'] = {k:v for k,v in saved['attempts'].items() if k in rows}
        # Clock rollback and restarts never reopen an already dispatched slot.
        if saved['last_slot'] is not None and epoch < saved['last_slot']:
            if saved != before:store.set_state(KEY, saved)
            return []
        saved['last_slot'] = epoch
        selected = []
        for identifier in groups[epoch % SLOTS]:
            row = rows[identifier]
            previous = saved['attempts'].get(identifier)
            if previous and (previous['generation'] == row['generation'] and epoch-previous['slot'] < SLOTS):
                continue
            if row['next_poll_at'] > now or store.provider_block('followings', row['username']):
                continue
            saved['attempts'][identifier] = {'generation':row['generation'], 'slot':epoch}
            selected.append(dict(row, batch_next_poll_at=(epoch+SLOTS)*SECONDS))
        if saved != before:store.set_state(KEY, saved)
        return selected
