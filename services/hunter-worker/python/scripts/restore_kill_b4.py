"""Actual SIGKILL at restore commit/publication boundaries; shared heavy lock required."""
import json,os,signal,subprocess,sys,time,uuid
from pathlib import Path
from hunterradar.store import Store,Conflict
from hunterradar.parsers import Follow,Target
from hunterradar.retention import backup_bundle,micros

module=Path(__file__).resolve().parents[1]
folder=module/'var/b4'/('restore-kill-'+uuid.uuid4().hex);folder.mkdir(mode=0o700)
store=Store(folder/'hunter.db',initialize=True);now=round(time.time(),3)
hunters=[]
for i in (1,2):
 row=store.add('kill_fixture'+str(i),now=now-100);store.apply_profile(row,str(100+i),'Synthetic',5000,now-100)
 row=store.hunter(row['id']);store.establish_wss_baseline([row],now-100);hunters.append(row)
def discover(handle,identifier):
 for row in hunters:store.ingest_wss(Follow(row['username'],Target(handle,identifier,'Synthetic',''),now,now,'6551_WSS',handle+row['id']))
discover('before','999');bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(now))
discover('after','888')
with store.connect() as db:latest=dict(db.execute("SELECT * FROM target_discovery_ledger WHERE x_user_id='888'").fetchone())
code="""import os,signal,sys
from pathlib import Path
from hunterradar.retention import restore_bundle
def checkpoint(stage):
 if stage==sys.argv[4]:os.kill(os.getpid(),signal.SIGKILL)
restore_bundle(Path(sys.argv[1]),Path(sys.argv[2]),current=Path(sys.argv[3]),progress=checkpoint)
"""
results=[]
for phase in ('after_copy','before_merge_commit','after_merge_commit','after_reservation','after_publish'):
 destination=folder/phase/'hunter.db'
 child=subprocess.run([sys.executable,'-c',code,str(bundle),str(destination),str(store.path),phase],cwd=folder,env={'PATH':os.environ['PATH'],'PYTHONPATH':str(module)},capture_output=True)
 assert child.returncode==-signal.SIGKILL,(phase,child.returncode,child.stderr.decode())
 if phase!='after_publish':
  try:Store(destination)
  except (ValueError,os.error):pass
  else:raise AssertionError('incomplete restore accepted: '+phase)
  for temp in destination.parent.glob('.hunter-restore-*.tmp'):
   try:Store(temp)
   except ValueError:pass
   else:raise AssertionError('staging accepted')
  results.append({'phase':phase,'signal':'SIGKILL','activation':'rejected'})
 else:
  restored=Store(destination)
  with restored.connect() as db:
   assert dict(db.execute("SELECT * FROM target_discovery_ledger WHERE x_user_id='888'").fetchone())==latest
   assert db.execute('SELECT count(*) FROM public_changes').fetchone()[0]==0
  try:restored.ingest_wss(Follow(hunters[0]['username'],Target('after','888','Synthetic',''),now+1,now+1,'6551_WSS','replay-after'))
  except Conflict:pass
  with restored.connect() as db:assert db.execute("SELECT count(*) FROM discoveries WHERE target='after'").fetchone()[0]==0
  results.append({'phase':phase,'signal':'SIGKILL','activation':'complete_fences_no_duplicate'})
output={'status':'passed','kill_cases':5,'before_publication_rejected':4,'after_publication_safe':1,'provider_calls':0,'cases':results}
(module/'docs/b4/restore-kill.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output))
