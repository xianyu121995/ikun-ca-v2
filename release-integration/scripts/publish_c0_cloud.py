#!/usr/bin/env python3
"""Publish only the approved NEW v2 tunnel after exact-owner Access was inspected."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from deploy_c0_lite import ROOT, TARGET, command, digest, write_private

LABEL = 'ca.ikun.v2.c0lite.tunnel'


def main():
    config = json.loads((TARGET / 'config/cloudflare.local.json').read_text())
    resources_path = ROOT / 'release-integration/.runtime/c0-lite/cloud-resources.json'
    resources = json.loads(resources_path.read_text())
    deployment = json.loads((ROOT / 'release-integration/.runtime/c0-lite/deployment.json').read_text())
    assert deployment['candidate_sha'] == command(['git', 'rev-parse', 'HEAD'], cwd=ROOT)
    assert config['hostname'] == 'v2.ikun.ca' and config['tunnel_uuid'] == resources['new_tunnel_uuid']
    assert config['access_policy_verified'] and config['access_exact_email_only']
    assert config['owner_email'] and '@' in config['owner_email'] and '*' not in config['owner_email']
    assert config['access_team'] and len(config['access_application_aud']) == 64
    credentials = Path(config['credentials_file'])
    assert credentials.parent == TARGET / 'config' and (credentials.stat().st_mode & 0o777) == 0o600
    assert json.loads(credentials.read_text())['TunnelID'] == config['tunnel_uuid']
    plist = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    assert not plist.exists() and not plist.is_symlink(), 'EXISTING_JOB_FILE_PRESERVED'
    domain = 'gui/' + str(os.getuid())
    assert subprocess.run(['/bin/launchctl', 'print', domain + '/' + LABEL], capture_output=True).returncode
    binary = TARGET / 'toolchains/cloudflared/cloudflared'
    binary.parent.mkdir(mode=0o700)
    shutil.copyfile('/opt/homebrew/bin/cloudflared', binary); binary.chmod(0o700)
    tunnel_config = Path(config['tunnel_config'])
    command([binary, 'tunnel', '--config', tunnel_config, 'ingress', 'validate'])
    text = tunnel_config.read_text()
    assert text.count('hostname:') == 1 and 'hostname: v2.ikun.ca' in text
    assert 'required: true' in text and config['access_application_aud'] in text and 'http_status:404' in text
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); metrics = probe.getsockname()[1]
    argv = [str(binary), 'tunnel', '--config', str(tunnel_config), '--no-autoupdate',
            '--metrics', '127.0.0.1:' + str(metrics), '--loglevel', 'warn', 'run', config['tunnel_uuid']]
    env = {'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8'}
    job = {'Label': LABEL, 'ProgramArguments': ['/usr/bin/env', '-i', *[k + '=' + v for k, v in env.items()], *argv],
           'WorkingDirectory': str(TARGET), 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30,
           'ExitTimeOut': 30, 'Umask': 0o077, 'ProcessType': 'Background', 'Nice': 5,
           'StandardOutPath': str(TARGET / 'logs/tunnel.log'), 'StandardErrorPath': str(TARGET / 'logs/tunnel.error.log')}
    write_private(plist, plistlib.dumps(job)); command(['/usr/bin/plutil', '-lint', plist])
    report = {'new_label': LABEL, 'new_tunnel_uuid': config['tunnel_uuid'], 'hostname': config['hostname'],
              'access_application_id': config['access_application_id'], 'owner_email': config['owner_email'],
              'access_team': config['access_team'], 'connector_jwt_required': True, 'binary_sha256': digest(binary),
              'config_sha256': digest(tunnel_config), 'candidate_sha': deployment['candidate_sha'],
              'existing_resources_changed': False, 'dns_created': False, 'authenticated_app_verified': False}
    loaded = False
    try:
        command(['/bin/launchctl', 'bootstrap', domain, plist]); loaded = True
        local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            try:
                with local.open('http://127.0.0.1:' + str(metrics) + '/ready', timeout=2) as response:
                    if response.status == 200: break
            except (OSError, ValueError): pass
            time.sleep(.5)
        else: raise RuntimeError('NEW_CONNECTOR_NOT_READY_NO_DNS_PUBLISHED')
        report['connector_ready'] = True
        # Cloudflare creates only the new exact record; never pass --overwrite-dns.
        command([binary, 'tunnel', '--origincert', TARGET / 'config/cert.pem', 'route', 'dns', config['tunnel_uuid'], 'v2.ikun.ca'], timeout=40)
        report['dns_created'] = True
        resources['dns_changed'] = True
        resources_path.write_text(json.dumps(resources, indent=2) + '\n')

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        public = urllib.request.build_opener(NoRedirect())
        checks = []
        for path in ('/', '/api/v1/projects', '/api/v1/events/stream'):
            result = None
            for _ in range(6):
                try:
                    response = public.open(urllib.request.Request('https://v2.ikun.ca' + path,
                                           headers={'Cf-Access-Authenticated-User-Email': config['owner_email']}), timeout=8)
                except urllib.error.HTTPError as error: response = error
                except OSError:
                    time.sleep(1); continue
                redirect = urllib.parse.urlparse(response.headers.get('Location', '')).hostname
                result = {'path': path, 'status': response.status, 'redirect_host': redirect,
                          'forged_email_header_did_not_authenticate': response.status in (301, 302, 303, 307, 308, 401, 403)}
                response.close(); break
            checks.append(result or {'path': path, 'network': 'UNVERIFIED'})
        report['anonymous_checks'] = checks
        expected = config['access_team'] + '.cloudflareaccess.com'
        report['anonymous_access_gate_verified'] = all(c.get('redirect_host') == expected and c.get('status') in (302, 303, 307, 308) for c in checks)
        report['status'] = 'PUBLISHED_ACCESS_LOGIN_PENDING' if report['anonymous_access_gate_verified'] else 'PUBLISHED_GATE_REVIEW_REQUIRED'
        deployment.update(public_status=report['status'], tunnel_created=True, dns_changed=True)
        (ROOT / 'release-integration/.runtime/c0-lite/deployment.json').write_text(json.dumps(deployment, indent=2) + '\n')
    except Exception as error:
        report['status'] = 'BLOCKED'; report['error'] = type(error).__name__
        # Before DNS, stop only our new connector. After DNS keep Access enforced.
        if loaded and not report['dns_created']:
            subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL], capture_output=True)
        raise
    finally:
        output = ROOT / 'release-integration/.runtime/c0-lite/cloud-publication.json'
        write_private(output, report)
        print(json.dumps({'receipt': str(output), 'status': report['status'], 'dns_created': report['dns_created']}))


if __name__ == '__main__':
    main()
