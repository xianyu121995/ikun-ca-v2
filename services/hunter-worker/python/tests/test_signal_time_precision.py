"""A second REST observation must qualify before any later clock advance."""
import json

import pytest

from conftest import ready
from hunterradar.parsers import Target
from hunterradar.retention import micros


@pytest.mark.parametrize('at', [1792831811.9798474, 1792832111.7397814, 1792836011.1462498])
def test_second_fractional_rest_signal_publishes_immediately(store, at):
    first = ready(store, 'hunter1', followers=0, user_id='101', now=at)
    second = ready(store, 'hunter2', followers=0, user_id='102', now=at)
    store.apply_poll(first, [], at-120)
    store.apply_poll(second, [], at-120)
    store.set_state('retention_clock_highwater', 0)
    target = Target('precision_project', '999')
    assert store.apply_poll(first, [target], at-60)['new'] == 1
    assert store.apply_poll(second, [target], at)['new'] == 1
    # Read persisted output directly: aggregate()/HTTP must not advance the clock
    # and hide an ingestion-time omission.
    with store.connect() as db:
        discovery = db.execute('SELECT * FROM discoveries WHERE target=?', (target.username,)).fetchone()
        assert discovery is not None
        changes = db.execute('SELECT data,initial_publication FROM public_changes WHERE entity_id=?',
                             (discovery['discovery_id'],)).fetchall()
        assert len(changes) == 1 and changes[0]['initial_publication'] == 1
        assert json.loads(changes[0]['data'])['signal_count'] == 2
        event = db.execute('SELECT occurred_at,received_at,window_at FROM follow_events WHERE hunter_id=?',
                           (second['id'],)).fetchone()
        assert event['occurred_at'] == event['received_at'] == at
        assert event['window_at'] == micros(at)/1e6
