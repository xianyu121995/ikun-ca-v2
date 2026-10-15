#!/usr/bin/env python3
"""Create one disposable v2 readonly viewer via real CLI; never save or print its password."""
import argparse
import getpass
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path
import pexpect
from deploy_c0_lite import ROOT, TARGET
from night_worker_ops import private_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--username',required=True)
    args=parser.parse_args()
    assert re.fullmatch(r'c0_b3_viewer_[0-9]{10}',args.username)
    owner=private_json(TARGET/'owner.json');env=private_json(TARGET/'config/web.environment.json')
    assert owner['candidate_sha']==env['IKUN_RELEASE_SHA']==args.expected_sha
    assert env['DATA_ROOT']==str(TARGET/'data') and env['IKUN_AUTH_ORIGIN']=='https://v2.ikun.ca' and 'IKUN_AUTH_DEV' not in env
    assert sys.stdin.isatty()
    final=getpass.getpass('临时只读账号口令（隐藏输入，不保存）：')
    assert len(final)>=24
    initial=secrets.token_urlsafe(32)
    child=pexpect.spawn(sys.executable,[str(ROOT/'release-integration/scripts/c0_auth.py'),'create','--username',args.username],encoding='utf-8',echo=False,timeout=30)
    try:
        child.expect('初始密码（至少10字符）：');child.sendline(initial)
        child.expect('再次输入密码：');child.sendline(initial)
        child.expect(pexpect.EOF);child.close();assert child.exitstatus==0
    finally:
        if child.isalive():child.close(force=True)
    code="""import{pathToFileURL}from'node:url';
const payload=JSON.parse(await new Promise(resolve=>{let body='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>body+=s);process.stdin.on('end',()=>resolve(body));}));
const root=process.argv[1];const{LocalAccounts}=await import(pathToFileURL(root+'/modules/auth/dist/src/local.js'));const{environment}=await import(pathToFileURL(root+'/modules/auth/dist/src/config.js'));const store=new LocalAccounts(environment());
try{const row=store.list().find(x=>x.username===payload.username);if(!row||row.role!=='user'||!row.enabled||!row.must_change_password)throw Error('NEW_VIEWER_ONLY');const session=await store.login(payload.username,payload.initial);await store.changePassword(session.actor,payload.initial,payload.final);const current=store.list().find(x=>x.username===payload.username);console.log(JSON.stringify({username:current.username,role:current.role,enabled:!!current.enabled,must_change_password:!!current.must_change_password,credential_saved:false}));}finally{store.close();}
"""
    result=subprocess.run([str(TARGET/'toolchains/node24/bin/node'),'--input-type=module','-e',code,str(TARGET/'releases'/args.expected_sha)],
                          input=json.dumps({'username':args.username,'initial':initial,'final':final}),env=env,capture_output=True,text=True,timeout=20)
    initial=final=''
    if result.returncode:
        cleanup=pexpect.spawn(sys.executable,[str(ROOT/'release-integration/scripts/c0_auth.py'),'disable','--username',args.username],encoding='utf-8',echo=False,timeout=30)
        cleanup.expect(pexpect.EOF);cleanup.close()
        raise RuntimeError('VIEWER_ACTIVATION_FAILED_DISABLED' if cleanup.exitstatus==0 else 'VIEWER_ACTIVATION_FAILED_DISABLE_REQUIRED')
    safe=json.loads(result.stdout);assert safe['role']=='user' and not safe['must_change_password']
    path=ROOT/'release-integration/.runtime/night-b3/public-temp-cycle.json'
    path.write_text(json.dumps(safe,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps(safe,ensure_ascii=False))


if __name__=='__main__':main()
