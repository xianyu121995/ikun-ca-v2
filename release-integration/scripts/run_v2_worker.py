#!/usr/bin/env python3
"""Load the owned private environment without putting credentials in argv."""
import json
import logging
import logging.handlers
import os
from pathlib import Path
import runpy
import sys
os.umask(0o077)
role=sys.argv[1]
if role not in ('hunter','tracking'):raise SystemExit('unknown worker')
root=Path(__file__).resolve().parents[2]
v2=Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
config=v2/'config'/(role+'.live.environment.json')
if config.stat().st_mode & 0o077:raise SystemExit('private environment required')
os.environ.update(json.loads(config.read_text()))
sys.path[:0]=[str(root/'packages/runtime/python'),str(root/'services'/f'{role}-worker/python')]
if role=='tracking':
    log=v2/'logs/tracking-target-raw.jsonl'
    handler=logging.handlers.RotatingFileHandler(log,maxBytes=8*1024*1024,backupCount=3,encoding='utf-8')
    logger=logging.getLogger('tracking.target.raw');logger.setLevel(logging.INFO);logger.propagate=False;logger.addHandler(handler)
    sys.argv=['tracking','serve','--config',os.environ['IKUN_TRACKING_CONFIG']]
    runpy.run_module('tracking.cli',run_name='__main__')
else:
    sys.argv=['hunterradar','run']
    runpy.run_module('hunterradar',run_name='__main__')
