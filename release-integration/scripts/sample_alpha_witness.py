"""Bounded local Alpha witness. Never connects to a provider or changes Alpha."""
from dataclasses import dataclass
from datetime import datetime, timezone
import copy
import math
import re
import uuid


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='microseconds')


@dataclass(frozen=True)
class Facts:
    pid: int
    started_utc: str
    connected: bool
    observed_at: float
    last_pong_at: float
    reconnect_count: int
    accounts_sha256: str

    def fresh(self, now):
        numbers = (now, self.observed_at, self.last_pong_at)
        return (all(type(x) in (int, float) and math.isfinite(x) for x in numbers)
                and type(self.pid) is int and self.pid > 0 and bool(self.started_utc)
                and self.connected is True and type(self.reconnect_count) is int
                and self.reconnect_count >= 0
                and bool(re.fullmatch('[a-f0-9]{64}', self.accounts_sha256))
                and -1 <= now - self.observed_at <= 5
                and -1 <= now - self.last_pong_at <= 45)


class Projection:
    """One witness epoch per reviewed baseline. Drift latches unhealthy permanently."""
    def __init__(self, baseline, *, now, epoch, run_id, hunter_exclusions, tracking_exclusions):
        if not baseline.fresh(now):
            raise ValueError('fresh baseline required')
        if any(str(uuid.UUID(x, version=4)) != x for x in (epoch, run_id)):
            raise ValueError('explicit UUID4 witness epoch and Hunter run required')
        if any(not re.fullmatch('[a-f0-9]{64}', x) for x in (hunter_exclusions, tracking_exclusions)):
            raise ValueError('exact domain exclusion bindings required')
        self.baseline, self.epoch, self.run_id = baseline, epoch, run_id
        self.hunter_exclusions, self.tracking_exclusions = hunter_exclusions, tracking_exclusions
        self.failed = False
        self.last_pong = baseline.last_pong_at
        self.last_observed = baseline.observed_at
        self.initial = self.tracking(True, baseline.observed_at)

    def tracking(self, healthy, observed_at):
        return dict(contract='tracking-sample-alpha-witness-v1', healthy=healthy,
                    connection_epoch=self.epoch, reconnect_count=self.baseline.reconnect_count,
                    exclusions_sha256=self.tracking_exclusions, observed_at=iso(observed_at))

    def project(self, facts, *, now):
        expected = self.baseline
        healthy = isinstance(facts, Facts) and facts.fresh(now)
        if healthy:
            healthy = (all(getattr(facts, x) == getattr(expected, x)
                           for x in ('pid', 'started_utc', 'reconnect_count', 'accounts_sha256'))
                       and facts.last_pong_at >= self.last_pong
                       and facts.observed_at >= self.last_observed)
        self.failed = self.failed or not healthy
        if healthy:
            self.last_pong, self.last_observed = facts.last_pong_at, facts.observed_at
        healthy = not self.failed
        hunter = dict(protocol='hunter-sample-alpha-guard-v1', execution_id='IKUN-ONLY-2026-10-16',
                      run_id=self.run_id, observed_at=iso(self.last_observed),
                      last_pong_at=iso(self.last_pong), healthy=healthy,
                      reconnect_count=expected.reconnect_count, exclusions_sha256=self.hunter_exclusions)
        return dict(hunter=hunter, tracking_initial=copy.deepcopy(self.initial),
                    tracking_rolling=self.tracking(healthy, self.last_observed),
                    stop_new_connections=not healthy)


def observe(plan):
    import hashlib
    import json
    import os
    from pathlib import Path
    import signal
    import time
    from takeover_backup import require,private_dir,atomic,artifact,utc
    from takeover_operator import ALPHA,System,same_process,ROOT
    require(type(plan['seconds']) is int and 1 <= plan['seconds'] <= 300,'WITNESS_DURATION_REJECTED')
    out=Path(plan['output']);require(out.is_absolute() and ROOT/'release-integration/.runtime/first-real-sample' in out.parents and not any(p.is_symlink()for p in (out,*out.parents)),'WITNESS_OUTPUT_REJECTED');private_dir(out)
    initial=out/'tracking.initial.json';require(not initial.exists(),'IMMUTABLE_INITIAL_ALREADY_EXISTS')
    def facts():
        expected=plan['expected_process'];current=System(None).process(expected['pid']);require(same_process(current,expected),'ALPHA_PROCESS_CHANGED')
        raw=ALPHA.read_bytes();roster=(ALPHA.parent/'accounts.json').read_bytes();require(len(raw)<=8_000_000 and len(roster)<=1_000_000,'ALPHA_LOCAL_FACTS_TOO_LARGE')
        require(hashlib.sha256(roster).hexdigest()==plan['accounts_sha256'],'ALPHA_ACCOUNTS_CHANGED')
        runtime=json.loads(raw)['runtime'];require(runtime['pid']==expected['pid'],'ALPHA_STATE_PID_CHANGED')
        return Facts(runtime['pid'],current['started_utc'],runtime['connected'],time.time(),runtime['last_pong_at'],runtime['reconnects'],plan['accounts_sha256'])
    baseline=facts();now=time.time();projection=Projection(baseline,now=now,epoch=plan['epoch'],run_id=plan['hunter_run_id'],hunter_exclusions=plan['hunter_exclusions_sha256'],tracking_exclusions=plan['tracking_exclusions_sha256'])
    fd=os.open(initial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(projection.initial,f,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    def publish(value):
        atomic(out/'hunter.guard.json',value['hunter']);atomic(out/'tracking.rolling.json',value['tracking_rolling'])
    first=projection.project(baseline,now=time.time());publish(first);atomic(out/'ready.private.json',{'state':'LOCAL_WITNESS_READY','at':utc(),'initial':artifact(initial),'new_wss_connections':0,'Alpha_writes':0});print(json.dumps({'state':'LOCAL_WITNESS_READY','initial_sha256':artifact(initial)['sha256'],'new_wss_connections':0}),flush=True)
    deadline=time.monotonic()+plan['seconds']
    try:
        while not stopping and time.monotonic()<deadline:
            try:value=projection.project(facts(),now=time.time())
            except Exception:value=projection.project(None,now=time.time())
            publish(value)
            if value['stop_new_connections']:raise RuntimeError('ALPHA_WITNESS_UNHEALTHY')
            time.sleep(1)
    finally:
        publish(projection.project(None,now=time.time()));atomic(out/'closed.private.json',{'state':'LOCAL_WITNESS_CLOSED_UNHEALTHY','at':utc(),'new_wss_connections':0,'Alpha_writes':0})


if __name__=='__main__':
    import argparse
    import json
    import os
    from pathlib import Path
    from takeover_backup import sha,require,read_json
    os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True);parser.add_argument('--observe',action='store_true');args=parser.parse_args();require(sha(Path(args.plan))==args.plan_sha256,'WITNESS_PLAN_HASH_CHANGED');plan=read_json(args.plan)
    if not args.observe:print(json.dumps({'state':'WITNESS_LOCAL_DRY_RUN_ONLY','seconds':plan['seconds'],'Alpha_writes':0,'new_wss_connections':0,'live_Alpha_reads':0}))
    else:
        try:observe(plan)
        except Exception as e:print(json.dumps({'state':'WITNESS_STOPPED','error_type':type(e).__name__,'new_wss_connections':0}));raise SystemExit(1)from None
