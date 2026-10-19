"""Independent four-store backup and local-only health for the AWS rehearsal."""
import datetime,json,os,pathlib,sqlite3,sys,time,urllib.request,shutil
from zoneinfo import ZoneInfo
root=pathlib.Path('/var/lib/ikun/test');os.umask(0o077)
if sys.argv[1]=='health':
 errors=[]
 try:
  origin=json.loads((root/'config/environment.json').read_text())['IKUN_AUTH_ORIGIN']
  req=urllib.request.Request('http://127.0.0.1:4000/health/ready',headers={'Host':urllib.parse.urlparse(origin).netloc})
  with urllib.request.urlopen(req,timeout=5) as response:assert response.status==200
 except Exception:errors.append('测试网站或项目服务不可用')
 stage=root/'ops/health.json.tmp';stage.write_text(json.dumps({'checked_at':time.time(),'healthy':not errors,'errors':errors}));stage.replace(root/'ops/health.json')
 print('TEST_HEALTH', 'OK' if not errors else 'FAILED');raise SystemExit(bool(errors))
elif sys.argv[1]=='backup':
 day=datetime.datetime.now(ZoneInfo("Asia/Shanghai"));base=root/'backups';daily=base/'daily';daily.mkdir(exist_ok=True)
 target=daily/day.strftime('%Y-%m-%d_%H%M%S');dest=daily/('.partial-'+str(os.getpid()));dest.mkdir(mode=0o700)
 for role in ('auth','projects','hunter','tracking'):
  with sqlite3.connect('file:'+str(root/'data'/role/(role+'.db'))+'?mode=ro',uri=True) as src,sqlite3.connect(dest/(role+'.db')) as out:
   src.backup(out);assert out.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not out.execute('PRAGMA foreign_key_check').fetchall()
 dest.rename(target);dest=target
 if day.weekday()==0:
  weekly=base/'weekly';weekly.mkdir(exist_ok=True);target=weekly/day.strftime('%G-W%V')
  if not target.exists():shutil.copytree(dest,target)
  for old in sorted(weekly.iterdir())[:-8]:shutil.rmtree(old)
 for old in daily.iterdir():
  if not old.name.startswith('.') and old.name<(day-datetime.timedelta(days=14)).strftime('%Y-%m-%d'):shutil.rmtree(old)
 print('TEST_BACKUP_OK')
else:raise SystemExit('UNKNOWN_OPERATION')
