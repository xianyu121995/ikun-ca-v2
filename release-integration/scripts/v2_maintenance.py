#!/usr/bin/env python3
"""Owned v2 online backups, bounded logs and local health checks."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

V2 = Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
BACKUPS = Path.home()/'Documents/ikun-ca-backups'
ZONE = ZoneInfo('Asia/Shanghai')
ROLES = ('auth','projects','hunter','tracking')

def private(path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    return path

def atomic(path,data):
    private(path.parent)
    temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as out:
        json.dump(data,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
    os.replace(temp,path)

def backup(root=V2,destination=BACKUPS,at=None):
    at=at or datetime.now(ZONE)
    daily=private(destination/'daily')
    name=at.strftime('%Y-%m-%d_%H%M%S')
    temp=daily/('.partial-'+name+'-'+str(os.getpid()));private(temp)
    try:
        for role in ROLES:
            path=root/'data'/role/(role+'.db')
            with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=10) as src, sqlite3.connect(temp/(role+'.db')) as dst:
                deadline=time.monotonic()+60
                def progress(status,remaining,total):
                    if time.monotonic()>deadline:raise TimeoutError('backup_timeout:'+role)
                src.backup(dst,pages=256,sleep=.05,progress=progress)
                if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or dst.execute('PRAGMA foreign_key_check').fetchone():
                    raise RuntimeError('backup_integrity_failed:'+role)
            (temp/(role+'.db')).chmod(0o600)
        os.rename(temp,daily/name)
        if at.weekday()==0:
            weekly=private(destination/'weekly');week=at.strftime('%G-W%V')
            if not (weekly/week).exists():
                stage=weekly/('.partial-'+week);shutil.copytree(daily/name,stage);os.rename(stage,weekly/week)
            for old in sorted(p for p in weekly.iterdir() if p.is_dir() and not p.name.startswith('.'))[:-8]:shutil.rmtree(old)
        threshold=(at-timedelta(days=14)).strftime('%Y-%m-%d_%H%M%S')
        for old in daily.iterdir():
            if old.is_dir() and not old.name.startswith('.') and old.name<threshold:shutil.rmtree(old)
        return daily/name
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True)
        raise

def get(url,headers=None):
    req=urllib.request.Request(url,headers=headers or {})
    with urllib.request.urlopen(req,timeout=8) as r:
        data=r.read(262144)
        if r.status!=200:raise RuntimeError('http_failure')
        return json.loads(data) if data.startswith(b'{') else {}

def rotate(root=V2,now=None):
    now=now or time.time()
    dirs=(root/'logs',root/'target-test/logs',root/'ops/logs')
    rotations=[]
    state_path=root/'ops/log-rotation.json'
    try:state=json.loads(state_path.read_text())
    except (OSError,ValueError):state={}
    day=datetime.fromtimestamp(now,ZONE).strftime('%Y-%m-%d')
    for folder in dirs:
        if not folder.is_dir():continue
        for path in folder.iterdir():
            if not path.is_file() or path.is_symlink():continue
            if '.archive-' in path.name or path.suffix.lstrip('.').isdigit():
                if now-path.stat().st_mtime>7*86400:path.unlink()
                else:rotations.append(path)
            elif path.stat().st_size and (path.stat().st_size>10*1024*1024 or state.get(str(path))!=day):
                target=path.with_name(path.name+'.archive-'+str(int(now)))
                with path.open('rb') as src,target.open('xb') as out:
                    src.seek(max(0,path.stat().st_size-10*1024*1024));shutil.copyfileobj(src,out)
                target.chmod(0o600)
                with path.open('r+b') as current:current.truncate(0)
                rotations.append(target)
                state[str(path)]=day
    atomic(state_path,state)
    total=sum(p.stat().st_size for p in rotations)
    for path in sorted(rotations,key=lambda p:p.stat().st_mtime):
        if total<=100*1024*1024:break
        total-=path.stat().st_size;path.unlink()

def health(root=V2):
    errors=[]
    for name,url in [('网站','http://127.0.0.1:4000/health/ready'),('猎手','http://127.0.0.1:4011/health/ready'),('追踪','http://127.0.0.1:4012/health/ready'),('隧道','http://127.0.0.1:65520/ready')]:
        try:get(url,{'Host':'v2.ikun.ca'} if name=='网站' else None)
        except Exception:errors.append(name+'服务不可用')
    try:
        e=json.loads((root/'config/web.environment.json').read_text())
        data=get('http://127.0.0.1:4012/internal/v1/subscriptions?limit=100',{'Authorization':'Bearer '+e['TRACKING_API_TOKEN']})['data']
        active=[r for r in data['items'] if r['desired_state']=='running']
        if any(r.get('error_code') for r in active):errors.append('追踪任务失败，请查看账号管理')
        if active and any(r['connection']!='connected' for r in active):errors.append('追踪监听中断')
        with sqlite3.connect('file:'+str(root/'data/hunter/hunter.db')+'?mode=ro',uri=True) as db:
            states={k:json.loads(v) for k,v in db.execute("SELECT key,value FROM state WHERE key IN ('worker_heartbeat','watch_error','watch_error_since','worker_error','wss_state')")}
            if time.time()-states.get('worker_heartbeat',0)>30:errors.append('猎手引擎心跳中断')
            # Owner request 2026-10-18: a single slow 6551 call retried within minutes is not an alert; only >15 min.
            if states.get('watch_error') and time.time()-(states.get('watch_error_since') or 0)>900:errors.append('猎手 Watch 同步异常（已持续 15 分钟以上）')
            if states.get('worker_error'):errors.append('猎手引擎任务异常')
            if db.execute("SELECT count(*) FROM hunters WHERE enabled=1 AND deleted_at IS NULL AND (poll_error IS NOT NULL OR profile_error IS NOT NULL)").fetchone()[0]:errors.append('猎手采集存在失败任务')
    except Exception:errors.append('监控任务健康状态无法读取')
    atomic(root/'ops/health.json',{'checked_at':time.time(),'healthy':not errors,'errors':errors})
    rotate(root)
    return errors

if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','health']);args=p.parse_args()
    if args.action=='backup':print('四库备份完成：',backup())
    else:
        errors=health();print('健康检查：', '；'.join(errors) or '正常')
