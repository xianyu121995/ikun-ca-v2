"""Prepare disabled systemd units and fresh test-only credentials on Lightsail."""
import json,os,pathlib,secrets,subprocess,pwd
assert os.getuid()==0
root=pathlib.Path('/var/lib/ikun/test');uid=pwd.getpwnam('ikun').pw_uid;gid=pwd.getpwnam('ikun').pw_gid
sha=pathlib.Path('/opt/ikun/current').resolve().name;token=secrets.token_urlsafe(48)
config=root/'config/environment.json';assert not config.exists(),'refusing to overwrite test configuration'
env={'DATA_ROOT':str(root/'data'),'IKUN_ENV':'isolated','IKUN_RELEASE_SHA':sha,'IKUN_AUTH_ORIGIN':'https://not-yet-assigned.invalid','IKUN_AUTH_TENANT_ID':'ikun-main','IKUN_AUTH_MAX_SESSIONS':'1','PROJECTS_PYTHON':'/opt/ikun/venvs/projects/bin/python','PROJECTS_DB':str(root/'data/projects/projects.db'),'IKUN_IPC_SOCKET':'/run/ikun-test-projects/projects.sock','IKUN_PROJECTS_IPC_SOCKET':'/run/ikun-test-projects/projects.sock','IKUN_IPC_TOKEN':token,'IKUN_PROJECTS_IPC_TOKEN':token,'IKUN_BUILD_SHA':sha,'IKUN_PROJECTS_BUILD_SHA':sha,'PORT':'4000'}
config.write_text(json.dumps(env));config.chmod(0o600);os.chown(config,uid,gid)
for name,obj in [('ai.json',{'provider':'codex','enabled':False}),('hunter.json',{'remote_enabled':False}),('tracking.json',{'remote_enabled':False,'db_path':str(root/'data/tracking/tracking.db')})]:
 p=root/'config'/name;p.write_text(json.dumps(obj));p.chmod(0o600);os.chown(p,uid,gid)
units=pathlib.Path('/etc/systemd/system');python='/opt/ikun/venvs/projects/bin/python';runner='/opt/ikun/bin/run_test.py';ops='/opt/ikun/bin/test_ops.py'
common='User=ikun\nGroup=ikun\nUMask=0077\nEnvironment=HOME=/var/lib/ikun TZ=Asia/Shanghai\nNoNewPrivileges=true\nPrivateTmp=true\nProtectHome=true\nProtectSystem=strict\nReadWritePaths=/var/lib/ikun/test /var/log/ikun /opt/ikun/current/apps/website/.next/cache\n'
for role in ('web','projects','hunter','tracking-live'):
 job='tracking' if role=='tracking-live' else role
 unit='[Unit]\nDescription=ikun isolated test '+role+'\nAfter=network-online.target\n'
 if role=='web':unit+='Requires=ikun-projects.service\nAfter=ikun-projects.service\n'
 if role in ('hunter','tracking-live'):unit+='ConditionPathExists=/etc/ikun/ENABLE_EXTERNAL_MONITORING\n'
 unit+='\n[Service]\n'+common
 if role=='projects':unit+='RuntimeDirectory=ikun-test-projects\nRuntimeDirectoryMode=0700\nExecStartPre=/usr/bin/rm -f /run/ikun-test-projects/projects.sock\n'
 unit+='ExecStart='+python+' '+runner+' '+job+'\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=30\nMemoryMax='+('1400M' if role=='web' else '512M')+'\n\n[Install]\nWantedBy=multi-user.target\n'
 (units/('ikun-'+role+'.service')).write_text(unit)
for role in ('health','backup'):
 (units/('ikun-'+role+'.service')).write_text('[Unit]\nDescription=ikun test '+role+'\n\n[Service]\nType=oneshot\n'+common+'ExecStart='+python+' '+ops+' '+role+'\n')
 timer='OnBootSec=60\nOnUnitActiveSec=60\n' if role=='health' else 'OnCalendar=*-*-* 04:00:00 Asia/Shanghai\nPersistent=true\n'
 (units/('ikun-'+role+'.timer')).write_text('[Unit]\nDescription=ikun test '+role+' schedule\n\n[Timer]\n'+timer+'\n[Install]\nWantedBy=timers.target\n')
(units/'ikun-test-tunnel.service').write_text('[Unit]\nDescription=Temporary Quick Tunnel for isolated migration test\nAfter=network-online.target\n\n[Service]\nUser=ikun\nGroup=ikun\nEnvironment=HOME=/var/lib/ikun\nExecStart=/usr/bin/cloudflared tunnel --url http://127.0.0.1:4000 --protocol http2 --no-autoupdate --metrics 127.0.0.1:65520\nRestart=on-failure\nRestartSec=5\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\n')
subprocess.run(['systemctl','daemon-reload'],check=True)
print('SYSTEMD_PREPARED_DISABLED; MONITORING_FENCE_ABSENT; AI_DISABLED')
