"""Verification helper for the project-monitor module's HTTP ingress.

The receiver owns its own transaction, actor policy, identity verification,
idempotency store and task execution. HunterRadar never opens its database.
"""
import hashlib
import hmac
import json
import time


def verify(body: bytes, headers, secret: str, now=None):
    now = time.time() if now is None else now
    if len(secret)<32 or len(body)>65536:
        raise ValueError('invalid_receiver_configuration_or_body')
    issued = headers.get('x-hunterradar-timestamp','')
    key = headers.get('idempotency-key','')
    signature = headers.get('x-hunterradar-signature','')
    if not issued.isdigit() or abs(now-int(issued))>300 or not key.startswith('hunterradar:'):
        raise ValueError('expired_or_invalid_command')
    expected = hmac.new(secret.encode(), issued.encode()+b'\n'+key.encode()+b'\n'+body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):
        raise ValueError('invalid_command_signature')
    command = json.loads(body)
    if (command.get('schema')!='hunterradar.project-task.v1' or command.get('manual_confirmed') is not True
            or command.get('action')!='request_project_monitoring' or 'hunterradar:'+command.get('command_id','')!=key):
        raise ValueError('invalid_command_contract')
    return command
