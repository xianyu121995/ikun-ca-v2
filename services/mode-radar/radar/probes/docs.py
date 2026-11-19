"""Docs / changelog watcher.

Both launchpads publish their feature catalog as documentation:
  * four.meme -> a GitBook `llms.txt` index (one line per page)
  * flap      -> a Docusaurus sidebar (no llms.txt, no sitemap.xml)

Three kinds of evidence are collected from the same fetch:
  1. page set   - a new URL = a new page = possibly a new mode
  2. content    - the index/whole page hash changed (a section was added
                  inside an existing page, which the URL set cannot see)
  3. addresses  - a new 0x... contract address appeared in a doc page that
                  lists deployed contracts = a new protocol deployment

First run records a baseline silently; later runs only report deltas.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse

from ..core.sanitize import safe_https
from .base import Probe, Signal

DOC_HOSTS = {
    "docs.flap.sh", "four-meme.gitbook.io", "raw.githubusercontent.com", "github.com",
}


def safe_doc_url(url: str) -> str:
    return safe_https(url, DOC_HOSTS)

LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
HREF_RE = re.compile(r'href="([^"#]+)"')
ADDR_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

HOT_DEFAULT = [
    "mode", "openfour", "tapefour", "protocol", "launch", "dock", "extension",
    "agent", "yield", "mining", "subscription", "royalty", "stock", "beta",
    "preview",
]


def _norm_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def parse_llms(text: str) -> dict:
    """{url: title} from a GitBook llms.txt style index."""
    out = {}
    for line in text.splitlines():
        for title, url in LINK_RE.findall(line):
            out[_norm_url(url)] = title.strip()
    return out


def parse_sitemap(text: str) -> dict:
    return {_norm_url(u): "" for u in LOC_RE.findall(text)}


def parse_html(text: str, base: str, prefix: str) -> dict:
    """Sidebar-style crawl: every internal link that starts with `prefix`."""
    out = {}
    for href in HREF_RE.findall(text):
        if not href.startswith(prefix):
            continue
        url = href if href.startswith("http") else base + href
        out[_norm_url(url)] = ""
    return out


def classify(url: str, title: str, hot, warm):
    blob = (url + " " + title).lower()
    if any(k in blob for k in hot):
        return "crit"
    if any(k in blob for k in warm):
        return "warn"
    return "info"


class DocsProbe(Probe):
    name = "docs"
    default_interval = 1800

    def run(self, ctx):
        signals = []
        for target in self.cfg.get("targets", []):
            if not target.get("enabled", True):
                continue
            try:
                signals += self._check(ctx, target)
            except Exception as e:  # noqa: BLE001 - one bad target must not stop the rest
                ctx.log(f"[docs] {target.get('name')} failed: {e}")
        return signals

    def _check(self, ctx, target):
        name = target["name"]
        source = f"docs:{name}"
        text = ctx.http.get_text(target["url"])
        mode = target.get("mode", "llms")

        if mode == "text":
            pages = {}
        elif mode == "sitemap":
            pages = parse_sitemap(text)
        elif mode == "html":
            parts = urllib.parse.urlsplit(target["url"])
            pages = parse_html(text, f"{parts.scheme}://{parts.netloc}",
                               target.get("href_prefix", "/"))
        else:
            pages = parse_llms(text)
        if not pages and mode != "text":
            raise RuntimeError("parsed 0 links - page format changed?")

        hot = target.get("hot", HOT_DEFAULT)
        warm = target.get("warm", ["guide", "developer", "integration", "update"])
        ignore = target.get("ignore", [])

        seeded = ctx.state.get_meta(f"docs_baseline:{name}")
        signals = []
        new_pages, changed_pages = [], []

        for url, title in pages.items():
            if any(k in url for k in ignore):
                continue
            state, old = ctx.state.observe(source, url, title)
            if state == "new":
                new_pages.append((url, title))
            elif state == "changed":
                changed_pages.append((url, old, title))

        content_digest = None
        content_changed = False
        if target.get("watch_content", True):
            content_digest = hashlib.sha1(
                text.encode("utf-8", "replace")
            ).hexdigest()[:16]
            st, _ = ctx.state.observe(source, "__content__", content_digest)
            content_changed = st == "changed"

        new_addrs = []
        if target.get("watch_addresses"):
            for addr in sorted({a.lower() for a in ADDR_RE.findall(text)}):
                st, _ = ctx.state.observe(source, f"addr:{addr}", addr)
                if st == "new":
                    new_addrs.append(addr)

        if not seeded:
            ctx.state.set_meta(f"docs_baseline:{name}", 1)
            ctx.state.set_meta(f"docs_count:{name}", len(pages))
            return [Signal(
                source=source, key="baseline", kind="baseline", level="info",
                title=f"已建立基线：{name}（{len(pages)} 页 / {len(new_addrs)} 个地址）",
                detail="首次运行，仅记录快照，不报增量。",
                url=safe_doc_url(target["url"]),
            )]

        for url, title in new_pages:
            signals.append(Signal(
                source=source, key=url, kind="new",
                level=classify(url, title, hot, warm),
                title=f"新文档页面：{title or url}",
                detail="可能是新模式/新玩法的预告页。",
                url=safe_doc_url(url), payload={"title": title}, fingerprint=url,
            ))

        for url, old, new in changed_pages:
            signals.append(Signal(
                source=source, key=url, kind="changed", level="warn",
                title=f"文档标题变更：{old or url} -> {new}",
                detail="页面被改写，可能加了新章节。",
                url=safe_doc_url(url), payload={"from": old, "to": new}, fingerprint=new,
            ))

        if content_changed and not new_pages:
            signals.append(Signal(
                source=source, key="__content__", kind="changed", level="warn",
                title=f"{name} 页面内容变化（无新增页面）",
                detail="现有页面被改写——新模式常常是加在一个老页面的章节里，"
                       "这种情况 URL 集合不变，只有内容哈希能发现。",
                url=safe_doc_url(target["url"]), payload={"digest": content_digest},
                fingerprint=content_digest,
            ))

        current = set(pages)
        if current:
            for key in ctx.state.list_keys(source):
                if not key.startswith("http") or key in current:
                    continue
                ctx.state.forget(source, key)
                signals.append(Signal(
                    source=source, key=key, kind="gone", level="warn",
                    title=f"文档页面删除：{key}",
                    detail="目录里不再有这个页面。",
                    url=safe_doc_url(key), fingerprint=f"gone:{key}",
                ))

        for addr in new_addrs:
            signals.append(Signal(
                source=source, key=f"addr:{addr}", kind="new", level="crit",
                title=f"{name} 文档里出现新合约地址 {addr}",
                detail="部署地址表新增条目 = 新协议/新组件已经在链上部署。",
                url=safe_doc_url(target["url"]), payload={"address": addr}, fingerprint=addr,
            ))
        return signals
