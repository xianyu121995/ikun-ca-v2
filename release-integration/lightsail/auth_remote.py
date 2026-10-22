#!/usr/bin/env python3
"""TTY-preserving desktop client for the production auth CLI on ikun-server."""
import os
import re
import shlex
import subprocess
import sys


COMMANDS = frozenset((
    'list', 'create', 'create-admin', 'reset-password', 'disable', 'enable',
    'recover-admin', 'bootstrap',  # Preserve the original first-admin tool.
))

# Only code and a validated command/username go in SSH argv. Password input goes
# straight from the user's terminal to the remote CLI, never through this client.
REMOTE = '''import json, os, pathlib, sys
os.umask(0o077)
base = pathlib.Path('/var/lib/ikun/production')
config = base / 'config/web.environment.json'
assert config.stat().st_mode & 0o077 == 0, 'private_configuration_required'
settings = json.loads(config.read_text())
assert settings.get('DATA_ROOT') == str(base / 'data'), 'production_data_root_required'
assert settings.get('IKUN_AUTH_ORIGIN') == 'https://ikun.ca', 'production_origin_required'
assert settings.get('IKUN_AUTH_DEV') != '1', 'production_auth_required'
root = pathlib.Path('/opt/ikun/current').resolve(strict=True)
cli = root / 'modules/auth/dist/src/cli.js'
assert cli.is_file() and (base / 'data/auth/auth.db').is_file(), 'production_auth_missing'
env = {'HOME':'/var/lib/ikun', 'TZ':'Asia/Shanghai', 'LANG':'C.UTF-8',
       'PATH':'/opt/ikun/toolchains/node24/bin:/usr/local/bin:/usr/bin:/bin'}
for key in ('DATA_ROOT', 'IKUN_AUTH_ORIGIN', 'IKUN_AUTH_TENANT_ID', 'IKUN_AUTH_MAX_SESSIONS'):
    if key in settings: env[key] = str(settings[key])
node = '/opt/ikun/toolchains/node24/bin/node'
os.chdir(root)
os.execve(node, [node, str(cli), *sys.argv[1:]], env)
'''


def validated_args(args):
    if args == ['list']:
        return args
    if (len(args) != 3 or args[0] not in COMMANDS - {'list'}
            or args[1] != '--username'):
        raise ValueError('账号命令无效，请从桌面工具菜单操作。')
    username = args[2].strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}', username):
        raise ValueError('用户名须为 3–32 位字母、数字、点、下划线或短横线。')
    return [args[0], '--username', username]


def ssh_argv(args):
    command = shlex.join([
        'sudo', '-n', '-H', '-u', 'ikun', '/opt/ikun/venvs/projects/bin/python',
        '-c', REMOTE, *validated_args(args),
    ])
    return [
        '/usr/bin/ssh', '-t', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=12',
        '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=2', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
        'ikun-server', command,
    ]


def main(args=None):
    try:
        argv = ssh_argv(sys.argv[1:] if args is None else args)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if not os.isatty(0) or not os.isatty(1):
        print('请在 Mac 终端中双击运行桌面账号工具，需要交互终端。', file=sys.stderr)
        return 2
    try:
        # Deliberately inherit the TTY; do not capture stdin/stdout, use a shell,
        # retry mutations, or write terminal output/passwords to a file.
        result = subprocess.run(argv, check=False).returncode
    except KeyboardInterrupt:
        print('\n已取消；若连接中断，请先查看账号列表确认结果。', file=sys.stderr)
        return 130
    except OSError:
        print('无法启动 SSH，请检查 Mac 的 SSH 和 ikun-server 配置。', file=sys.stderr)
        return 1
    if result == 255:
        print('无法连接东京服务器或连接已中断，请检查网络和 ikun-server SSH 钥匙。'
              '\n不会改用 Mac 旧库，也不会自动重试；请先查看服务器账号列表确认结果。',
              file=sys.stderr)
    elif result:
        print('服务器账号操作未完成，请查看上方提示；先查看账号列表再决定是否重试。',
              file=sys.stderr)
    return result if result >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())
