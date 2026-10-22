import contextlib
import importlib.util
import io
from pathlib import Path
import shlex
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('auth_remote', Path(__file__).with_name('auth_remote.py'))
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class RemoteAuthTests(unittest.TestCase):
    def test_all_operations_use_current_server_cli_as_service_user(self):
        for command in client.COMMANDS:
            with self.subTest(command=command):
                args = [command] if command == 'list' else [command, '--username', 'Friend_1']
                argv = client.ssh_argv(args)
                self.assertIn('-t', argv)
                self.assertEqual(argv[-2], 'ikun-server')
                remote = shlex.split(argv[-1])
                self.assertEqual(remote[:7], ['sudo', '-n', '-H', '-u', 'ikun', '/opt/ikun/venvs/projects/bin/python', '-c'])
                self.assertEqual(remote[7], client.REMOTE)
                self.assertEqual(remote[8:], ['list'] if command == 'list' else [command, '--username', 'friend_1'])
                self.assertNotIn('c0_auth.py', argv[-1])
                self.assertNotIn('Application Support', argv[-1])

    def test_rejects_shell_and_unapproved_arguments_before_ssh(self):
        for args in (['create', '--username', 'x;touch /tmp/bad'], ['list', '--username', 'admin'],
                     ['migrate'], ['create', '--password', 'never-log-this'],
                     ['create', '--username', 'ab'], ['create-admin', '--username', 'abc\nxyz']):
            with self.subTest(args=args), patch.object(client.subprocess, 'run') as run:
                output = io.StringIO()
                with contextlib.redirect_stderr(output):
                    self.assertEqual(client.main(args), 2)
                run.assert_not_called()
                self.assertNotIn('never-log-this', output.getvalue())

    def test_inherits_terminal_without_capture_pipe_shell_or_retry(self):
        with patch.object(client.os, 'isatty', return_value=True), patch.object(
                client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(client.main(['list']), 0)
            run.assert_called_once_with(client.ssh_argv(['list']), check=False)

    def test_no_tty_fails_before_connection(self):
        with patch.object(client.os, 'isatty', return_value=False), patch.object(client.subprocess, 'run') as run:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(client.main(['list']), 2)
            run.assert_not_called()

    def test_connection_failure_explains_chinese_no_fallback(self):
        with patch.object(client.os, 'isatty', return_value=True), patch.object(
                client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 255)) as run:
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                self.assertEqual(client.main(['list']), 255)
            self.assertIn('无法连接东京服务器', output.getvalue())
            self.assertIn('不会改用 Mac 旧库', output.getvalue())
            run.assert_called_once()

    def test_remote_wrapper_compiles_and_only_executes_existing_auth(self):
        compile(client.REMOTE, '<remote-auth>', 'exec')
        self.assertIn('/opt/ikun/current', client.REMOTE)
        self.assertIn('modules/auth/dist/src/cli.js', client.REMOTE)
        self.assertIn('os.execve', client.REMOTE)
        self.assertNotIn('input(', client.REMOTE)
        self.assertNotIn('print(', client.REMOTE)


if __name__ == '__main__':
    unittest.main()
