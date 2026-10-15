#!/usr/bin/env python3
"""Run accepted B2 bypass-Proxy/SSE assertions against actual received app files."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from c0_test_fixture import ROOT, NODE, PYTHON, provision, migrate_projects, environment


def main():
    work=Path(tempfile.mkdtemp(prefix='ikun-c0-entries-',dir='/private/tmp'))
    data=work/'data';origin='http://127.0.0.1:31997';credentials=work/'synthetic.secret.json'
    accounts=provision(data,origin,credentials);migrate_projects(data)
    env={**environment(data,origin),'PROJECTS_PYTHON':str(PYTHON),'TEST_ACCOUNTS':str(credentials),
         'B2_BUILD_SHA':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    activated=subprocess.run([str(NODE),str(ROOT/'release-integration/scripts/activate_guard_fixture.mjs'),str(data),origin,str(credentials)],
                              cwd=ROOT,env=env,capture_output=True,timeout=30)
    if activated.returncode:raise RuntimeError('DIRECT_ENTRY_FIXTURE_ACTIVATION_FAILED')
    accounts=json.loads(credentials.read_text())
    command=[str(NODE),'--import',str(ROOT/'node_modules/tsx/dist/loader.mjs'),'--test',
             '--test-name-pattern','Actual|Seven-day|Local B1|Password change|B0 rejects',
             str(ROOT/'release-integration/c0-lite/tests/entry-guards.test.mjs')]
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
    output=result.stdout+result.stderr
    for account in accounts.values():output=output.replace(account['password'],'<redacted>')
    output=re.sub(r'ikun_dev_session=[^\s;\'"}]+','ikun_dev_session=<redacted>',output)
    prefix=ROOT/('release-integration/c0-lite/evidence/entries-'+str(int(time.time()*1000)))
    prefix.with_suffix('.tap').write_text(output)
    record={'status':'PASS' if result.returncode==0 else 'FAIL','command':command,'exit_code':result.returncode,
            'tests':re.findall(r'ℹ (?:tests|pass|fail|skipped) \d+',output),'runtime':str(work),
            'scope':'actual received Route Handlers/Server Action and real B0 UDS, Proxy bypassed, isolated synthetic credentials'}
    prefix.with_suffix('.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':record['status'],'report':str(prefix.with_suffix('.json')),'counts':record['tests']},ensure_ascii=False))
    return result.returncode


if __name__=='__main__':sys.exit(main())
