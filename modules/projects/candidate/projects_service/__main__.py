import argparse
import json
import os
import re
from pathlib import Path

from .db import Database


def main():
    parser = argparse.ArgumentParser(description='独立主页项目服务；仅访问 projects.db')
    parser.add_argument('--db', default=os.environ.get('PROJECTS_DB', 'data/projects.db'))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate')
    provision = commands.add_parser('create-client')
    provision.add_argument('--role', choices=['superadmin','user'])
    provision.add_argument('--source')
    provision.add_argument('--tenant', default='default')
    provision.add_argument('--out', required=True, help='凭证写入新建的 0600 本地文件，不输出凭证')
    revoke = commands.add_parser('revoke-client')
    revoke.add_argument('principal_id')
    serve = commands.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8120)
    args = parser.parse_args()
    db = Database(args.db)
    if args.command == 'serve':
        import uvicorn
        from .api import Settings, create_app
        config = Settings.from_env()
        config = Settings(db_path=args.db, origin=config.origin, secure_cookie=config.secure_cookie, proxy_authority=config.proxy_authority)
        uvicorn.run(create_app(config), host=args.host, port=args.port, access_log=False, proxy_headers=False, timeout_graceful_shutdown=10)
        return
    if args.command == 'create-client':
        if bool(args.role) == bool(args.source) or (args.source and not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', args.source)):
            parser.error('用户凭证指定 --role；独立服务凭证指定 --source，两者不能同时指定')
        out = Path(args.out).absolute()
        if out.suffix != '.json' or out == db.path:
            parser.error('凭证输出必须是独立的 .json 新文件')
        out.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents silently overwriting a working credential.
        fd = os.open(out, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            db.migrate()
            principal_id, token = db.create_principal(args.role, args.source, args.tenant)
            with os.fdopen(fd, 'w') as file:
                json.dump({'principal_id': principal_id, 'tenant_id': args.tenant, 'role': args.role, 'source': args.source, 'token': token}, file, indent=2)
                file.write('\n')
        except BaseException:
            out.unlink(missing_ok=True)
            raise
        print(f'凭证已写入 {out}（权限 0600）')
    elif args.command == 'revoke-client':
        with db.transaction() as con:
            changed = con.execute('UPDATE principals SET disabled=1 WHERE id=?', (args.principal_id,)).rowcount
            con.execute('DELETE FROM sessions WHERE principal_id=?', (args.principal_id,))
        if not changed:
            parser.error('凭证 ID 不存在')
        print('凭证及会话已停用')
    else:
        db.migrate()
        print('projects.db 迁移完成')


if __name__ == '__main__':
    main()
