"""Discover new public repositories under verified GitHub owners.

Owners come only from explicit config, which must be backed by an official
site or docs link. A GitHub link found later in those docs is a clue: it can
name a repo under an already verified owner, and it cannot add a new owner or
start a web-wide search. Repository contents are never fetched or executed.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlsplit

from ..core.sanitize import redact, safe_https
from .base import Probe, Signal

API = "https://api.github.com"
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
LINK_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=/|[?#\s\"'<>)]|$)"
)
DOC_HOSTS = {"docs.flap.sh", "four-meme.gitbook.io"}
MAX_PAGES = 10
PER_PAGE = 100


def _repo_name(repo):
    return bool(REPO_RE.fullmatch(repo or "")) and repo not in {".", ".."} and ".." not in repo


def verified_owner(login, allowed):
    login = (login or "").strip()
    if not LOGIN_RE.fullmatch(login):
        return ""
    allowed_set = {item.lower() for item in allowed or []}
    return login if login.lower() in allowed_set else ""


def parse_github_links(text, allowed_logins):
    """Keep only https://github.com/<verified-owner>/<repo>. Ignore every other link."""
    found = {}
    if not isinstance(text, str):
        return found
    for login, repo in LINK_RE.findall(text):
        owner = verified_owner(login, allowed_logins)
        if not owner or not _repo_name(repo):
            continue
        found.setdefault(owner, set()).add(repo)
    return found


def parse_any_github_repo(text):
    """Strict repo links for human review. These are not owners and are not crawled."""
    out = []
    if not isinstance(text, str):
        return out
    seen = set()
    for login, repo in LINK_RE.findall(text):
        if not LOGIN_RE.fullmatch(login) or not _repo_name(repo):
            continue
        full = f"{login}/{repo}"
        if full.lower() in seen:
            continue
        seen.add(full.lower())
        out.append(full)
    return out


def _safe_repo_url(login, repo):
    if not verified_owner(login, [login]) or not _repo_name(repo):
        return ""
    return safe_https(f"https://github.com/{login}/{repo}", {"github.com"})


def _doc_url(url):
    cleaned = safe_https(url or "", DOC_HOSTS)
    if not cleaned:
        return ""
    parts = urlsplit(cleaned)
    if parts.username or parts.password or parts.query or parts.fragment:
        return ""
    return cleaned


class DiscoverProbe(Probe):
    name = "discover"
    default_interval = 3600

    def run(self, ctx):
        if not self.cfg.get("enabled", True):
            return []
        now = time.time()
        until = ctx.state.get_meta("discover_backoff_until")
        if until and now < int(until):
            ctx.log("[discover] 仍在 GitHub 限流退避中，本轮不请求")
            return []
        signals = []
        owners = [item for item in (self.cfg.get("owners") or []) if item.get("enabled", True) and item.get("login")]
        for owner in owners:
            try:
                signals += self._owner(ctx, owner)
            except Exception as exc:  # noqa: BLE001
                ctx.log(f"[discover] {owner.get('login')} 失败，不把失败当成删除: {exc}")
        for clue in self.cfg.get("doc_clues") or []:
            try:
                signals += self._doc_clue(ctx, clue)
            except Exception as exc:  # noqa: BLE001
                ctx.log(f"[discover] 文档线索失败，不把失败当成删除: {exc}")
        return signals

    def _owner(self, ctx, owner):
        login = verified_owner(owner.get("login"), [owner.get("login")])
        project = redact(owner.get("project") or login, 40) or login
        if not login:
            return []
        evidence = _doc_url((owner.get("evidence") or [""])[0])
        source = f"github-discover:{project}"
        listed = self._list_repos(ctx, login)
        if listed is None:
            return []
        if listed.get("not_modified"):
            return []
        repos = listed["repos"]
        seeded = ctx.state.get_meta(f"discover_baseline:{login}")
        if not seeded:
            for full in repos:
                ctx.state.observe(source, f"repo:{full}", full)
            ctx.state.set_meta(f"discover_baseline:{login}", 1)
            return [Signal(
                source=source, key="baseline", kind="baseline", level="info",
                title=f"已建立 {project} 官方仓库基线：{login}（{len(repos)} 个公开仓库）",
                detail="首次只记录仓库名单，不把已有仓库报成新发现，也不读取仓库内容。",
                url=f"https://github.com/{login}",
                fingerprint="discover-baseline",
            )]
        out = []
        for full in repos:
            state, _old = ctx.state.observe(source, f"repo:{full}", full)
            if state != "new":
                continue
            name = full.split("/", 1)[1]
            out.append(Signal(
                source=source, key=f"repo:{full}", kind="new", level="crit",
                title=f"{project} 官方账号 {login} 新增公开仓库 {name}",
                detail=redact(
                    f"官方依据：{evidence or '配置中的已核实 owner'}。只通知仓库出现，不读取、不执行仓库内容。",
                    400,
                ),
                url=_safe_repo_url(login, name),
                payload={"project": project, "login": login, "repo": name, "evidence": evidence},
                fingerprint=full,
            ))
        return out

    def _list_repos(self, ctx, login):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ikun-mode-radar",
        }
        token = self.cfg.get("token") or ""
        if token:
            headers["Authorization"] = "Bearer " + token
        pages = int(ctx.state.get_meta(f"discover_pages:{login}") or "1")
        etag = ctx.state.get_meta(f"discover_etag:{login}") or ""
        if pages == 1 and etag:
            headers["If-None-Match"] = etag
        collected = []
        seen = set()
        for page in range(1, MAX_PAGES + 1):
            url = f"{API}/users/{login}/repos?per_page={PER_PAGE}&page={page}&type=owner&sort=created&direction=asc"
            status, hdrs, body = ctx.http.conditional_get(url, headers=headers)
            self._note_budget(ctx, hdrs)
            if status == 304 and page == 1:
                return {"not_modified": True, "repos": []}
            if status in (403, 429):
                self._backoff(ctx, hdrs)
                return None
            if status != 200:
                ctx.log(f"[discover] {login} 第 {page} 页 HTTP {status}，本轮放弃，不报删除")
                return None
            try:
                payload = json.loads(body.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                return None
            if not isinstance(payload, list):
                return None
            page_etag = hdrs.get("etag") if page == 1 else ""
            for item in payload:
                if not isinstance(item, dict) or item.get("fork") or item.get("private"):
                    continue
                full = str(item.get("full_name") or "")
                owner_name, _, repo = full.partition("/")
                if owner_name.lower() != login.lower() or not _repo_name(repo):
                    continue
                key = f"{login}/{repo}"
                if key.lower() in seen:
                    continue
                seen.add(key.lower())
                collected.append(key)
            headers.pop("If-None-Match", None)
            if len(payload) < PER_PAGE:
                ctx.state.set_meta(f"discover_pages:{login}", page)
                if page == 1 and page_etag:
                    ctx.state.set_meta(f"discover_etag:{login}", page_etag)
                return {"not_modified": False, "repos": collected}
            if str(hdrs.get("x-ratelimit-remaining") or "") == "0":
                self._backoff(ctx, hdrs)
                return None
        ctx.log(f"[discover] {login} 超过 {MAX_PAGES} 页，本轮不更新基线")
        return None

    def _doc_clue(self, ctx, clue):
        url = _doc_url(clue.get("url"))
        project = redact(clue.get("project") or "文档", 40)
        if not url:
            return []
        allowed = [verified_owner(item, [item]) for item in (clue.get("allowed_logins") or [])]
        allowed = [item for item in allowed if item]
        text = ctx.http.get_text(url)
        source = f"github-discover:{project}"
        seeded = ctx.state.get_meta(f"discover_doc_baseline:{url}")
        verified = parse_github_links(text, allowed)
        unverified = [
            full for full in parse_any_github_repo(text)
            if full.split("/", 1)[0].lower() not in {item.lower() for item in allowed}
        ]
        if not seeded:
            for login, names in verified.items():
                for name in names:
                    ctx.state.observe(source, f"repo:{login}/{name}", f"{login}/{name}")
            for full in unverified:
                ctx.state.observe(source, f"clue:{full}", full)
            ctx.state.set_meta(f"discover_doc_baseline:{url}", 1)
            return [Signal(
                source=source, key="doc-baseline", kind="baseline", level="info",
                title=f"已记录 {project} 官方文档中的 GitHub 链接",
                detail="未核实的账号不会被加入扫描。首次不把已有链接报成新仓库。",
                url=url, fingerprint=f"doc-baseline:{url}",
            )]
        out = []
        for login, names in verified.items():
            for name in sorted(names):
                full = f"{login}/{name}"
                state, _old = ctx.state.observe(source, f"repo:{full}", full)
                if state != "new":
                    continue
                out.append(Signal(
                    source=source, key=f"repo:{full}", kind="new", level="crit",
                    title=f"{project} 官方文档新增已核实仓库 {full}",
                    detail=f"线索来自官方文档 {url}，owner {login} 已在配置中核实。不读取仓库内容。",
                    url=_safe_repo_url(login, name),
                    payload={"project": project, "login": login, "repo": name, "evidence": url},
                    fingerprint=full,
                ))
        for full in unverified:
            state, _old = ctx.state.observe(source, f"clue:{full}", full)
            if state != "new":
                continue
            out.append(Signal(
                source=source, key=f"clue:{full}", kind="new", level="info",
                title=f"{project} 官方文档出现未核实 GitHub 链接 {full}",
                detail="没有把它当成官方账号，也没有扩大仓库扫描。",
                url="",
                payload={"project": project, "unverified": full, "evidence": url},
                fingerprint=f"clue:{full}",
            ))
        return out

    def _note_budget(self, ctx, headers):
        remaining = headers.get("x-ratelimit-remaining")
        if remaining is not None and str(remaining).isdigit() and int(remaining) <= 1:
            self._backoff(ctx, headers)

    def _backoff(self, ctx, headers):
        reset = headers.get("x-ratelimit-reset")
        if reset and str(reset).isdigit():
            ctx.state.set_meta("discover_backoff_until", int(reset))
        else:
            ctx.state.set_meta("discover_backoff_until", int(time.time()) + 3600)
        ctx.log("[discover] GitHub 限流，退避到额度恢复，不报删除")
