"""Real Chromium checks against an isolated production Next build; no business DBs."""
import json
import hashlib
import os
import pty
import select
import socket
import sqlite3
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
PASSWORD = "test-init1"
CHANGED = "test-next2"
PREVIEW_MANIFEST = json.loads((MODULE / "test-results/b1-preview.json").read_text())
PREVIEW = Path(PREVIEW_MANIFEST["preview"])


def local_cli(env, command, name=None, value=None, expected=0):
    """Real PTY; test-only passphrases are never argv/env or terminal output."""
    master, slave = pty.openpty()
    args = [NODE, "modules/auth/dist/src/cli.js", command]
    if name:
        args += ["--username", name]
    process = subprocess.Popen(args, cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = bytearray()
    try:
        if value is not None:
            for prompt in ["初始密码", "再次输入密码"]:
                deadline = time.monotonic() + 15
                while prompt.encode() not in output:
                    if time.monotonic() > deadline:
                        raise RuntimeError("CLI hidden prompt missing")
                    if select.select([master], [], [], 0.1)[0]:
                        output.extend(os.read(master, 4096))
                while termios.tcgetattr(master)[3] & termios.ECHO:
                    if time.monotonic() > deadline:
                        raise RuntimeError("CLI echo remained enabled")
                    time.sleep(0.01)
                os.write(master, (value + "\r").encode())
        deadline = time.monotonic() + 15
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise RuntimeError("CLI did not finish")
            if select.select([master], [], [], 0.1)[0]:
                try:
                    output.extend(os.read(master, 4096))
                except OSError:
                    break
        process.wait(timeout=5)
        assert process.returncode == expected, output.decode(errors="replace")
        if value:
            assert value.encode() not in output, "CLI echoed fictional test password"
        return output.decode(errors="replace")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        os.close(master)


def login(page, origin, name, value, forced=False):
    page.goto(origin + "/login")
    page.locator('input[name="username"]').fill(name)
    page.locator('input[name="password"]').fill(value)
    page.get_by_role("button", name="登录", exact=True).click()
    page.wait_for_url("**/auth/password" if forced else origin + "/")


def change_password(page, origin, current, new):
    page.goto(origin + "/auth/password")
    for name in ["new_password", "confirm_password"]:
        field = page.locator(f'input[name="{name}"]')
        assert field.get_attribute("minlength") == "10"
        assert field.get_attribute("maxlength") == "128"
        field.fill("x" * 9)
        assert field.evaluate("el => el.validity.tooShort")
    page.locator('input[name="current_password"]').fill(current)
    page.locator('input[name="new_password"]').fill(new)
    page.locator('input[name="confirm_password"]').fill(new)
    page.get_by_role("button", name="保存新密码", exact=True).click()
    page.wait_for_url("**/?notice=password_changed")


def api(context, origin, path, method="GET", data=None):
    headers = {"Origin": origin}
    if method != "GET":
        me = context.request.get(origin + "/api/v1/auth/me")
        if me.ok:
            headers["X-CSRF-Token"] = me.json()["data"]["csrf_token"]
    return context.request.fetch(origin + path, method=method, data=data, headers=headers)


def fallback_checks(browser, origin, cookies, artifacts):
    results = []
    for mode in ["javascript_disabled", "chunks_blocked"]:
        ctx = browser.new_context(java_script_enabled=mode != "javascript_disabled")
        ctx.add_cookies(cookies)
        if mode == "chunks_blocked":
            ctx.route("**/_next/static/**/*.js", lambda route: route.abort())
        for path, action in [("/login", "/api/v1/auth/login"), ("/auth/password", "/api/v1/auth/password")]:
            page = ctx.new_page()
            marker = "fictional-fallback-password-96138"
            requests = []
            page.on("request", lambda r: requests.append(r))
            page.goto(origin + path)
            form = page.locator("form").first
            assert form.get_attribute("method").lower() == "post"
            assert form.get_attribute("action") == action
            for element in form.locator("input").all():
                element.fill("no_js_user" if element.get_attribute("name") == "username" else marker)
            with page.expect_navigation() as nav:
                form.locator("[type=submit]").click()
            assert nav.value.status == 415
            assert marker not in nav.value.text()
            assert all(marker not in r.url for r in requests)
            assert [r for r in requests if r.is_navigation_request()][-1].method == "POST"
            history = ctx.new_cdp_session(page).send("Page.getNavigationHistory")
            assert all(marker not in entry["url"] for entry in history["entries"])
            assert marker not in (artifacts / "next-smoke.log").read_text()
            results.append({"mode": mode, "path": path, "status": 415, "password_not_in_url_history_response_log": True})
            page.close()
        ctx.close()
    return results


def main():
    artifacts = MODULE / "test-results" / f"b1-final-browser-{int(time.time()*1000)}"
    artifacts.mkdir()
    for name, expected in PREVIEW_MANIFEST["inputs"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, "source changed; rebuild preview"
    with tempfile.TemporaryDirectory(prefix="ikun-auth-final-next-", dir="/private/tmp") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {**os.environ, "DATA_ROOT": str(Path(temp) / "data"), "IKUN_AUTH_DEV": "1", "IKUN_AUTH_ORIGIN": origin, "NEXT_TELEMETRY_DISABLED": "1"}
        assert len(PASSWORD) == len(CHANGED) == 10
        local_cli(env, "bootstrap", "root_admin", "x" * 9, expected=1)
        prompt = local_cli(env, "bootstrap", "root_admin", PASSWORD)
        assert "至少10字符" in prompt
        db_path = Path(env["DATA_ROOT"]) / "auth/auth.db"
        local_cli(env, "create", "rejected_user", "x" * 9, expected=1)
        local_cli(env, "create", "viewer", PASSWORD)
        local_cli(env, "reset-password", "viewer", "x" * 9, expected=1)
        local_cli(env, "recover-admin", "root_admin", "x" * 9, expected=1)
        listing = local_cli(env, "list")
        assert "viewer" in listing and "root_admin" in listing
        assert "password_hash" not in listing and PASSWORD not in listing
        local_cli(env, "disable", "root_admin", expected=1)
        with (artifacts / "next-smoke.log").open("w") as log:
            process = subprocess.Popen([NODE, str(PREVIEW / "apps/website/node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", str(port)], cwd=PREVIEW / "apps/website", env=env, stdout=log, stderr=log)
            try:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError("Next exited before ready")
                    try:
                        with urllib.request.urlopen(origin + "/health/live", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Next readiness timeout")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("IKUN_TEST_CHROMIUM") or None)
                    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    for route in ["/", "/hunter", "/tracking"]:
                        page.goto(origin + route)
                        page.wait_for_url("**/login?next=*")
                    assert api(ctx, origin, "/api/v1/projects").status == 401
                    assert api(ctx, origin, "/internal/v1/auth-guard-probe", "POST", {}).status == 401
                    page.goto(origin + "/login")
                    page.screenshot(path=artifacts / "login-desktop.png", full_page=True)
                    page.locator('input[name="username"]').fill("ghost")
                    page.locator('input[name="password"]').fill(PASSWORD)
                    page.get_by_role("button", name="登录", exact=True).click()
                    page.get_by_text("用户名或密码错误", exact=True).wait_for()
                    page.screenshot(path=artifacts / "login-error-desktop.png", full_page=True)
                    login(page, origin, "root_admin", PASSWORD, forced=True)
                    assert api(ctx, origin, "/api/v1/projects").status == 403
                    for route in ["/", "/hunter", "/tracking"]:
                        page.goto(origin + route)
                        page.wait_for_url("**/auth/password")
                    page.screenshot(path=artifacts / "initial-password-desktop.png", full_page=True)
                    page.goto(origin + "/internal/v1/action-probe")
                    page.get_by_role("button", name="执行鉴权测试").click()
                    page.wait_for_url("**/internal/v1/action-probe?result=403")
                    old_cookies = ctx.cookies()
                    change_password(page, origin, PASSWORD, CHANGED)
                    assert api(ctx, origin, "/api/v1/auth/me").ok
                    old = browser.new_context()
                    old.add_cookies(old_cookies)
                    assert api(old, origin, "/api/v1/auth/me").status == 401
                    old.close()
                    assert page.locator('nav[aria-label="业务导航"] a').count() == 3
                    assert page.get_by_text("账号管理", exact=True).count() == 0
                    page.locator("summary").click()
                    page.get_by_role("link", name="修改本人密码").wait_for()
                    page.get_by_role("button", name="退出登录").wait_for()
                    page.screenshot(path=artifacts / "admin-shell-desktop.png", full_page=True)
                    assert api(ctx, origin, "/api/v1/projects", "POST", {}).status == 200
                    assert api(ctx, origin, "/internal/v1/auth-guard-probe", "POST", {}).status == 200
                    for path in ["/api/v1/auth/users", "/api/v1/auth/users/usr_test/reset-password"]:
                        assert api(ctx, origin, path, "POST", {}).status == 404
                    page.goto(origin + "/auth/users")
                    assert "404" in page.content() or "不存在" in page.content()
                    page.goto(origin + "/internal/v1/action-probe")
                    page.get_by_role("button", name="执行鉴权测试").click()
                    page.wait_for_url("**/internal/v1/action-probe?result=200")
                    page.locator('input[name="csrf_token"]').evaluate("el => el.value = 'invalid'")
                    page.get_by_role("button", name="执行鉴权测试").click()
                    page.wait_for_url("**/internal/v1/action-probe?result=403")
                    # Native fallback of both actual public-component password forms.
                    fallbacks = fallback_checks(browser, origin, ctx.cookies(), artifacts)
                    # Emergency CLI recovery works while all web sessions are active.
                    local_cli(env, "recover-admin", "root_admin", PASSWORD)
                    assert api(ctx, origin, "/api/v1/auth/me").status == 401
                    login(page, origin, "root_admin", PASSWORD, forced=True)
                    change_password(page, origin, PASSWORD, CHANGED)
                    page.goto(origin + "/auth/password")
                    page.locator("summary").click()
                    page.get_by_role("button", name="退出登录").click()
                    page.wait_for_url("**/login")
                    assert api(ctx, origin, "/api/v1/projects").status == 401
                    # Reader uses real CLI-created account and must change password.
                    login(page, origin, "viewer", PASSWORD, forced=True)
                    change_password(page, origin, PASSWORD, CHANGED)
                    assert api(ctx, origin, "/api/v1/projects").status == 200
                    assert api(ctx, origin, "/api/v1/projects", "POST", {}).status == 403
                    assert api(ctx, origin, "/internal/v1/auth-guard-probe", "POST", {}).status == 403
                    page.goto(origin + "/internal/v1/action-probe")
                    page.get_by_role("button", name="执行鉴权测试").click()
                    page.wait_for_url("**/internal/v1/action-probe?result=403")
                    for route in ["/", "/hunter", "/tracking"]:
                        page.goto(origin + route)
                        assert page.locator('nav[aria-label="业务导航"] a').count() == 3
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.screenshot(path=artifacts / "reader-shell-mobile.png", full_page=True)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.goto(origin + "/auth/password")
                    page.screenshot(path=artifacts / "password-mobile.png", full_page=True)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    # Local disable revokes a cookie immediately; enable does not revive it.
                    saved = ctx.cookies()
                    local_cli(env, "disable", "viewer")
                    assert api(ctx, origin, "/api/v1/auth/me").status == 401
                    failed = api(ctx, origin, "/api/v1/auth/login", "POST", {"username": "viewer", "password": CHANGED})
                    assert failed.status == 401 and failed.json()["error"]["message"] == "用户名或密码错误"
                    local_cli(env, "enable", "viewer")
                    assert api(ctx, origin, "/api/v1/auth/me").status == 401
                    login(page, origin, "viewer", CHANGED)
                    local_cli(env, "reset-password", "viewer", PASSWORD)
                    assert api(ctx, origin, "/api/v1/projects").status == 401
                    login(page, origin, "viewer", PASSWORD, forced=True)
                    assert api(ctx, origin, "/api/v1/projects").status == 403
                    change_password(page, origin, PASSWORD, CHANGED)
                    # Assert actual seven-day stored duration, then simulate clock passing in this temp DB.
                    with sqlite3.connect(db_path) as db:
                        durations = db.execute("SELECT expires_at-created_at FROM auth_sessions").fetchall()
                        assert durations and all(row[0] == 604800 for row in durations)
                        db.execute("UPDATE auth_sessions SET created_at=created_at-604800,last_seen=last_seen-604800,expires_at=expires_at-604800")
                    assert api(ctx, origin, "/api/v1/projects").status == 401
                    page.goto(origin + "/")
                    page.wait_for_url("**/login?next=*")
                    page.get_by_text("请登录，原会话可能已过期。", exact=True).wait_for()
                    page.screenshot(path=artifacts / "expired-login-mobile.png", full_page=True)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    # HTTP readiness must not perform a migration or write schema metadata.
                    with sqlite3.connect(db_path) as db:
                        before = db.execute("SELECT * FROM _schema_migrations").fetchall()
                    for _ in range(3):
                        assert ctx.request.get(origin + "/health/ready").status == 200
                    with sqlite3.connect(db_path) as db:
                        assert before == db.execute("SELECT * FROM _schema_migrations").fetchall()
                    for secret in [PASSWORD, CHANGED, "fictional-fallback-password-96138"]:
                        assert secret not in (artifacts / "next-smoke.log").read_text()
                    assert not errors, errors
                    browser.close()
                assert sorted(p.name for p in Path(env["DATA_ROOT"]).iterdir()) == ["auth"]
                result = {"password_minimum_10": "passed", "new_password_minlength_10": "passed", "cli_9_rejected_10_accepted": "passed", "passed": True, "next_production_browser": "passed", "cli_hidden_tty_all_seven_operations": "passed", "server_action_without_proxy": "passed", "route_handler_without_proxy": "passed", "self_password_rotates_session": "passed", "seven_day_expiry": "passed", "initial_and_reset_force_change": "passed", "removed_management_endpoints": "passed", "public_ui_actual_forms": "passed", "desktop": "1440x1000", "mobile": "390x844", "fallback_cases": fallbacks, "page_errors": errors, "business_databases_created": 0, "source_inputs": PREVIEW_MANIFEST["inputs"], "artifacts": str(artifacts)}
                (artifacts / "browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
                (MODULE / "test-results/b1-final-v2-browser.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
                print(json.dumps({k: v for k, v in result.items() if k != "source_inputs"}, ensure_ascii=False))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
