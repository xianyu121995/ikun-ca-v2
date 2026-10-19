"""Install approved Linux production services without starting or enabling them."""
import os
import subprocess
from pathlib import Path

assert os.getuid() == 0
units = Path('/etc/systemd/system')
saved = Path('/var/lib/ikun/production/ops/before-production-units')
saved.mkdir(mode=0o700, exist_ok=True)
common = '''User=ikun
Group=ikun
UMask=0077
Environment=HOME=/var/lib/ikun TZ=Asia/Shanghai
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/ikun /var/log/ikun /opt/ikun/current/apps/website/.next/cache
'''
for role in ('web', 'projects', 'hunter', 'tracking-live'):
    job = 'tracking' if role == 'tracking-live' else role
    unit = '[Unit]\nDescription=ikun production '+role+'\nWants=network-online.target\nAfter=network-online.target\n'
    if role == 'web':
        unit += 'Requires=ikun-projects.service\nAfter=ikun-projects.service\n'
    if role in ('hunter', 'tracking-live'):
        unit += 'ConditionPathExists=/var/lib/ikun/production/ops/EXTERNAL_MONITORING_APPROVED\n'
    unit += '\n[Service]\n'+common
    if role == 'projects':
        unit += 'RuntimeDirectory=ikun-production-projects\nRuntimeDirectoryMode=0700\nExecStartPre=/usr/bin/rm -f /run/ikun-production-projects/projects.sock\n'
    unit += 'ExecStart=/opt/ikun/venvs/'+('projects' if job in ('web', 'projects') else job)+'/bin/python /opt/ikun/bin/run_production.py '+job+'\n'
    unit += 'Restart=on-failure\nRestartSec=5\nTimeoutStopSec=90\nMemoryMax='+('1400M' if role=='web' else '512M' if role=='projects' else '1024M')+'\n\n[Install]\nWantedBy=multi-user.target\n'
    path = units/('ikun-'+role+'.service')
    if path.exists() and not (saved/path.name).exists():
        (saved/path.name).write_bytes(path.read_bytes())
    path.write_text(unit)
for role in ('health', 'backup'):
    unit = '[Unit]\nDescription=ikun production '+role+'\n\n[Service]\nType=oneshot\n'+common+'ExecStart=/opt/ikun/venvs/projects/bin/python /opt/ikun/bin/production_ops.py '+role+'\n'
    path = units/('ikun-'+role+'.service')
    if path.exists() and not (saved/path.name).exists():
        (saved/path.name).write_bytes(path.read_bytes())
    path.write_text(unit)
    interval = 'OnBootSec=60\nOnUnitActiveSec=60\n' if role=='health' else 'OnCalendar=*-*-* 04:00:00 Asia/Shanghai\nPersistent=true\n'
    (units/('ikun-'+role+'.timer')).write_text('[Unit]\nDescription=ikun production '+role+' schedule\n\n[Timer]\n'+interval+'\n[Install]\nWantedBy=timers.target\n')
(units/'ikun-tunnel.service').write_text('''[Unit]
Description=ikun production existing named tunnel
Wants=network-online.target
After=network-online.target ikun-web.service

[Service]
'''+common+'''ExecStart=/usr/bin/cloudflared tunnel --config /var/lib/ikun/production/config/cloudflared.yml --no-autoupdate --metrics 127.0.0.1:65520 --loglevel warn run
Restart=on-failure
RestartSec=5
TimeoutStopSec=45

[Install]
WantedBy=multi-user.target
''')
subprocess.run(['systemctl', 'daemon-reload'], check=True)
print('PRODUCTION_UNITS_INSTALLED_NOT_STARTED')
