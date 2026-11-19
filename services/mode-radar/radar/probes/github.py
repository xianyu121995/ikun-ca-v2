"""GitHub probe - the earliest public trace of a new mode.

four.meme ships its protocol as open repositories:
  * fourmeme-docs  -> abi/, contracts/interfaces/, docs/      (classic protocol)
  * openfour-docs  -> contracts/token/*.sol, contracts/modules/**,
                      contracts/taxstrategy/, contracts/taxvault/vaults/

A new `contracts/token/*.sol` or a new module directory appears in a commit
weeks before the feature is announced. So we diff the git tree: a new path is
a candidate new mode, a changed sensitive file is a rewrite of an existing one.
"""

from __future__ import annotations

import re

from ..core.sanitize import redact
from .base import Probe, Signal

API = "https://api.github.com"

CRIT_PATH = re.compile(
    r"(contracts/(token|modules|taxstrategy|taxvault|curve)/.*\.sol$"
    r"|abi/.*\.json$)",
    re.I,
)
WARN_PATH = re.compile(r"(contracts/.*\.sol$|docs/.*\.md$|scripts/.*\.(js|json)$)", re.I)
SENSITIVE_CHANGE = re.compile(
    r"(contracts/.*\.sol$"
    r"|abi/.*\.json$"
    r"|scripts/.*(abi|tags|registry).*\.(js|json)$"
    r"|docs/.*(mode|protocol|launch|tax|stock|module).*\.(md|json)$)",
    re.I,
)


class GithubProbe(Probe):
    name = "github"
    default_interval = 1800

    def _headers(self):
        h = {"Accept": "application/vnd.github+json"}
        token = self.cfg.get("token") or ""
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def run(self, ctx):
        signals = []
        for repo in self.cfg.get("repos", []):
            if not repo.get("enabled", True):
                continue
            try:
                signals += self._check(ctx, repo)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"[github] {repo['repo']} failed: {e}")
        return signals

    def _check(self, ctx, repo_cfg):
        repo = repo_cfg["repo"]
        branch = repo_cfg.get("branch", "main")
        source = f"github:{repo}"
        url = f"{API}/repos/{repo}/git/trees/{branch}?recursive=1"
        data = ctx.http.get_json(url, headers=self._headers())
        blobs = {t["path"]: t["sha"] for t in data.get("tree", []) if t.get("type") == "blob"}
        if not blobs:
            raise RuntimeError("empty tree")

        seeded = ctx.state.get_meta(f"github_baseline:{repo}")
        new_paths, changed = [], []
        for path, sha in blobs.items():
            state, _ = ctx.state.observe(source, path, sha)
            if state == "new":
                new_paths.append(path)
            elif state == "changed":
                changed.append(path)

        if not seeded:
            ctx.state.set_meta(f"github_baseline:{repo}", 1)
            return [Signal(
                source=source, key="baseline", kind="baseline", level="info",
                title=f"已建立仓库基线：{repo}（{len(blobs)} 个文件）",
                detail="首次运行，仅记录文件树。",
                url=_repo_url(repo, branch, "", "repo"),
            )]

        out = []
        for path in new_paths:
            if CRIT_PATH.search(path):
                level = "crit"
            elif WARN_PATH.search(path):
                level = "warn"
            else:
                level = "info"
            out.append(Signal(
                source=source, key=f"path:{path}", kind="new", level=level,
                title=redact(f"{repo} 新增文件 {path}", 300),
                detail="新增合约/ABI/文档通常意味着新模式正在开发或即将上线。",
                url=_repo_url(repo, branch, path, "blob"),
                payload={"path": path}, fingerprint=path,
            ))
        for path in changed:
            if not SENSITIVE_CHANGE.search(path):
                continue
            out.append(Signal(
                source=source, key=f"changed:{path}", kind="changed", level="warn",
                title=redact(f"{repo} 修改了敏感文件 {path}", 300),
                detail="现有合约/ABI/模式文档被改写，可能加了新模式字段。",
                url=_repo_url(repo, branch, path, "commits"),
                payload={"path": path}, fingerprint=blobs[path],
            ))
        live = set(blobs)
        for path in ctx.state.list_keys(source):
            if path in live or path.startswith("__"):
                continue
            ctx.state.forget(source, path)
            out.append(Signal(
                source=source, key=f"gone:{path}", kind="gone", level="warn",
                title=redact(f"{repo} 删除文件 {path}", 300),
                detail="文件从当前分支树里消失。",
                url=_repo_url(repo, branch, path, "commits"),
                payload={"path": path}, fingerprint=f"gone:{path}",
            ))
        return out


def _repo_url(repo, branch, path, kind):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", branch or ""):
        return ""
    if path and (".." in path.split("/") or not re.fullmatch(r"[A-Za-z0-9_.\-/+]+", path)):
        return ""
    if kind == "repo":
        return f"https://github.com/{repo}"
    if kind == "blob":
        return f"https://github.com/{repo}/blob/{branch}/{path}"
    if kind == "commits":
        return f"https://github.com/{repo}/commits/{branch}/{path}"
    return ""
