"""Real Chromium checks against an isolated production Next build; no business DBs."""
import json
import os
import pty
import select
import socket
import subprocess
import tempfile
import termios
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

MODULE = Path(__file__).resolve().parents[1]
ROOT = MODULE.parents[1]
NODE = os.environ.get("IKUN_NODE", "node")
PASSWORD = "ui-test-initial-long-passphrase"
CHANGED = "ui-test-changed-long-passphrase"
PREVIEW = MODULE / "test-results/next-preview"


def bootstrap_cli(env):
    """Exercise the real hidden-input CLI, assert no echo, and seed only temporary auth.db."""
    master, slave = pty.openpty()
    process = subprocess.Popen([NODE, "modules/auth/dist/src/cli.js", "bootstrap", "--username", "root_admin"],
                               cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = bytearray()
    try:
        for prompt in ["超级管理员密码", "再次输入密码"]:
            deadline = time.monotonic() + 10
            while prompt.encode() not in output:
                if time.monotonic() > deadline:
                    raise RuntimeError("bootstrap CLI did not present hidden-input prompt")
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 4096))
            while termios.tcgetattr(master)[3] & termios.ECHO:
                if time.monotonic() > deadline:
                    raise RuntimeError("bootstrap CLI did not disable terminal echo")
                time.sleep(0.01)
            os.write(master, (PASSWORD + "\r").encode())
        deadline = time.monotonic() + 10
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise RuntimeError("bootstrap CLI did not complete")
            if select.select([master], [], [], 0.1)[0]:
                try:
                    output.extend(os.read(master, 4096))
                except OSError:
                    break
        process.wait(timeout=5)
        assert process.returncode == 0, "bootstrap CLI failed"
        assert PASSWORD.encode() not in output, "bootstrap CLI echoed a test password"
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        os.close(master)


def main():
    with tempfile.TemporaryDirectory(prefix="ikun-auth-next-", dir="/private/tmp") as temporary:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {**os.environ, "DATA_ROOT": str(Path(temporary) / "data"), "IKUN_AUTH_DEV": "1",
               "IKUN_AUTH_ORIGIN": origin, "IKUN_AUTH_TENANT_ID": "ikun-main", "NEXT_TELEMETRY_DISABLED": "1"}
        bootstrap_cli(env)
        artifacts = MODULE / "test-results"
        with (artifacts / "next-smoke.log").open("w") as log:
            process = subprocess.Popen([NODE, str(PREVIEW / "apps/website/node_modules/next/dist/bin/next"),
                                        "start", "--hostname", "127.0.0.1", "--port", str(port)],
                                       cwd=PREVIEW / "apps/website", env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("isolated Next server exited; inspect next-smoke.log")
                    try:
                        with urllib.request.urlopen(origin + "/login", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError("isolated Next server did not become ready")
                with sync_playwright() as playwright:
                    executable = os.environ.get("IKUN_TEST_CHROMIUM")
                    browser = playwright.chromium.launch(headless=True,
                        **({"executable_path": executable} if executable else {}))
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(origin + "/")
                    page.wait_for_url("**/login?next=*")
                    assert page.evaluate("async () => (await fetch('/api/v1/projects')).status") == 401
                    page.goto(origin + "/auth")
                    page.wait_for_url("**/login?next=*")
                    page.screenshot(path=artifacts / "login-desktop.png", full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=artifacts / "login-mobile.png", full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.get_by_label("用户名", exact=True).fill("root_admin")
                    page.get_by_label("密码", exact=True).fill(PASSWORD)
                    page.get_by_role("button", name="显示密码").click()
                    assert page.locator("#password").get_attribute("type") == "text"
                    page.get_by_role("button", name="隐藏密码").click()
                    page.get_by_role("button", name="登录", exact=True).click()
                    page.wait_for_url("**/auth")
                    page.get_by_role("link", name="管理用户", exact=True).click()
                    page.get_by_role("button", name="创建用户").click()
                    page.get_by_label("用户名", exact=True).fill("viewer")
                    page.get_by_label("临时密码", exact=True).fill(PASSWORD)
                    page.get_by_label("确认临时密码", exact=True).fill(PASSWORD)
                    page.get_by_role("dialog").get_by_role("button", name="创建用户", exact=True).click()
                    row = page.locator("#users tr").filter(has_text="viewer")
                    row.wait_for()
                    row.get_by_role("button", name="禁用", exact=True).click()
                    page.get_by_role("dialog").get_by_role("button", name="禁用用户", exact=True).click()
                    row.get_by_role("button", name="启用", exact=True).wait_for()
                    row.get_by_role("button", name="启用", exact=True).click()
                    page.get_by_role("dialog").get_by_role("button", name="启用用户", exact=True).click()
                    row.get_by_role("button", name="禁用", exact=True).wait_for()
                    row.get_by_role("button", name="重置密码", exact=True).click()
                    page.get_by_label("临时密码", exact=True).fill(CHANGED)
                    page.get_by_label("确认临时密码", exact=True).fill(CHANGED)
                    page.get_by_role("dialog").get_by_role("button", name="重置密码", exact=True).click()
                    page.get_by_role("dialog").wait_for(state="hidden")
                    page.screenshot(path=artifacts / "users-desktop.png", full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    row.get_by_role("button", name="重置密码", exact=True).wait_for(state="visible")
                    page.screenshot(path=artifacts / "users-mobile.png", full_page=True)
                    page.get_by_role("button", name="退出登录").click()
                    page.wait_for_url("**/login")
                    page.get_by_label("用户名", exact=True).fill("viewer")
                    page.get_by_label("密码", exact=True).fill(CHANGED)
                    page.get_by_role("button", name="登录", exact=True).click()
                    page.wait_for_url("**/auth/password")
                    page.get_by_label("当前密码", exact=True).fill(CHANGED)
                    page.get_by_label("新密码", exact=True).fill(PASSWORD)
                    page.get_by_label("确认新密码", exact=True).fill(PASSWORD)
                    page.get_by_role("button", name="保存新密码").click()
                    page.wait_for_url("**/auth")
                    page.get_by_text("普通用户", exact=True).wait_for()
                    assert page.get_by_role("link", name="管理用户", exact=True).is_hidden()
                    assert page.evaluate("async () => (await fetch('/api/v1/auth/users')).status") == 403
                    assert page.evaluate("async () => (await fetch('/api/v1/tracking/subscriptions', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status") == 403
                    page.get_by_role("button", name="退出登录").click()
                    page.wait_for_url("**/login")
                    assert page.evaluate("async () => (await fetch('/api/v1/auth/me')).status") == 401
                    assert not errors, errors
                    browser.close()
                assert sorted(item.name for item in (Path(temporary) / "data").iterdir()) == ["auth"]
                result = {"next_production_browser": "passed", "bootstrap_hidden_tty": "passed", "desktop": "1440x1000", "mobile": "390x844",
                          "business_databases_created": 0, "page_errors": errors}
                (artifacts / "browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
                print(json.dumps(result, ensure_ascii=False))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
