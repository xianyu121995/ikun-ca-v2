#!/usr/bin/env python3
"""Run the accepted B1 CLI against only the new C0-lite runtime, keeping its TTY."""
import json
import os
from pathlib import Path
import sys

target = Path.home() / 'Library/Application Support/ikun-ca-v2-c0-lite'
env = json.loads((target / 'config/web.environment.json').read_text())
owner = json.loads((target / 'owner.json').read_text())
release = target / 'releases' / owner['candidate_sha']
assert env['DATA_ROOT'] == str(target / 'data')
assert env['IKUN_AUTH_ORIGIN'] == 'https://v2.ikun.ca' and 'IKUN_AUTH_DEV' not in env
node = str(target / 'toolchains/node24/bin/node')
os.execve(node, [node, str(release / 'modules/auth/dist/src/cli.js'), *sys.argv[1:]], env)
