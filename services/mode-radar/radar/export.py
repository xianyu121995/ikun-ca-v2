"""Export the radar state to a standalone HTML dashboard (and optional JSON).

The HTML is a single self-contained file - no CDN, no build step - so it can be
dropped straight into a web root (`/var/www/...`) and served by nginx/caddy.
"""

from __future__ import annotations

import html
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .core.sanitize import safe_https

BEIJING = ZoneInfo("Asia/Shanghai")

LEVEL_COLOR = {"crit": "#ff5c5c", "warn": "#ffb020", "info": "#4da3ff"}
LEVEL_TEXT = {"crit": "高危", "warn": "注意", "info": "信息"}


def _fmt_ts(ts, fmt="%m-%d %H:%M"):
    if not ts:
        return "—"
    return datetime.fromtimestamp(int(ts), BEIJING).strftime(fmt) + " 北京时间"


def collect(cfg, state, limit=300):
    """Gather everything the dashboard needs from config + sqlite."""
    now = int(time.time())
    events = state.recent_events(limit)

    probes_cfg = cfg.get("probes") or {}
    docs = [
        {"name": t["name"], "url": t["url"], "mode": t.get("mode", "llms"),
         "baseline": bool(state.get_meta("docs_baseline:" + t["name"]))}
        for t in (probes_cfg.get("docs") or {}).get("targets", [])
        if t.get("enabled", True)
    ]
    repos = [
        {"repo": r["repo"], "branch": r.get("branch", "main"),
         "baseline": bool(state.get_meta("github_baseline:" + r["repo"]))}
        for r in (probes_cfg.get("github") or {}).get("repos", [])
        if r.get("enabled", True)
    ]

    contracts, chains = [], []
    known_names = {}
    events_watched = []
    for chain, ccfg in ((probes_cfg.get("onchain") or {}).get("chains") or {}).items():
        if not ccfg.get("enabled", True):
            continue
        chains.append({
            "chain": chain,
            "cursor": state.get_meta("cursor:" + chain),
            "ids": len(ccfg.get("contracts") or []),
        })
        for c in ccfg.get("contracts") or []:
            ident = state.get("onchain:" + chain, "identity:" + c["name"]) or {}
            contracts.append({
                "chain": chain, "name": c["name"], "address": c["address"],
                "impl": ident.get("impl", ""), "code": (ident.get("code") or "")[:18],
            })
        for ev in ccfg.get("events") or []:
            events_watched.append({"chain": chain, "name": ev["name"],
                                   "signature": ev["signature"]})
            for w in ev.get("watch") or []:
                for k, v in (w.get("known") or {}).items():
                    known_names[(ev["name"], w.get("label", ""), str(k).lower())] = v

    registries = []
    for row in state.db.execute(
        "SELECT source, key FROM obs WHERE source LIKE 'onchain:%' AND key LIKE 'enum:%'"
        " ORDER BY key LIMIT 400"
    ):
        key = row["key"][5:]  # strip 'enum:'
        if "=" not in key:
            continue
        left, value = key.split("=", 1)
        ev_name, _, label = left.partition(":")
        name = known_names.get((ev_name, label, value.lower()), "")
        registries.append({
            "chain": row["source"].split(":", 1)[1],
            "event": ev_name, "label": label, "value": value,
            "known": name, "is_new": not name,
        })

    total = len(events)
    crit = sum(1 for e in events if e["level"] == "crit")
    day_ago = now - 86400
    last24 = sum(1 for e in events if e["ts"] >= day_ago)

    return {
        "generated_at": now,
        "overview": {
            "events": total, "crit": crit, "last24": last24,
            "contracts": len(contracts), "docs": len(docs), "repos": len(repos),
            "outbox": state.outbox_size(),
        },
        "chains": chains, "contracts": contracts,
        "docs": docs, "repos": repos, "events_watched": events_watched,
        "registries": registries,
        "alerts": [
            {"ts": e["ts"], "level": e["level"], "source": e["source"],
             "title": e["title"], "detail": e["detail"] or "", "url": e["url"] or ""}
            for e in events
        ],
    }


def write_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


CSS = """
:root{--bg:#0a0e13;--card:#121a23;--line:#1f2b38;--fg:#e6edf3;--mut:#8b98a5;
--crit:#ff5c5c;--warn:#ffb020;--info:#4da3ff;--ok:#35c26a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,
BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 60px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:12px;margin-bottom:6px}
h1{font-size:22px;margin:0;letter-spacing:.5px}
.sub{color:var(--mut);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .n{font-size:24px;font-weight:600;line-height:1.2}
.card .k{color:var(--mut);font-size:12px;margin-top:2px}
h2{font-size:15px;margin:30px 0 10px;color:var(--fg);font-weight:600;
border-left:3px solid var(--info);padding-left:9px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:500;font-size:12px}
tr:hover td{background:#0f1720}
.lv{font-size:11px;padding:1px 7px;border-radius:20px;white-space:nowrap}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
a{color:var(--info);text-decoration:none}
a:hover{text-decoration:underline}
.mut{color:var(--mut)}
.tag{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 6px;color:var(--mut)}
.new{color:var(--warn);border-color:#4a3410;background:#2a1f08}
.filters{display:flex;gap:8px;margin-bottom:10px}
.filters button{background:#101922;color:var(--mut);border:1px solid var(--line);
border-radius:7px;padding:5px 11px;cursor:pointer;font-size:12px}
.filters button.on{color:var(--fg);border-color:#2e4a68;background:#152234}
footer{margin-top:40px;color:var(--mut);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
"""

JS = """
function flt(lv,btn){document.querySelectorAll('.filters button').forEach(b=>b.classList.remove('on'));
btn.classList.add('on');
document.querySelectorAll('#alerts tbody tr').forEach(tr=>{
tr.style.display=(lv=='all'||tr.dataset.lv==lv)?'':'none';});}
"""


def render_html(data):
    o = data["overview"]
    e = html.escape

    def card(n, k):
        return f'<div class="card"><div class="n">{e(str(n))}</div><div class="k">{e(k)}</div></div>'

    rows = []
    for a in data["alerts"]:
        color = LEVEL_COLOR.get(a["level"], "#888")
        lv = LEVEL_TEXT.get(a["level"], a["level"])
        title = e(a["title"])
        href = safe_https(a.get("url") or "")
        if href:
            title = f'<a href="{e(href)}" target="_blank" rel="noopener noreferrer">{title}</a>'
        detail = f'<div class="mut mono">{e(a["detail"])}</div>' if a["detail"] else ""
        rows.append(
            f'<tr data-lv="{e(a["level"])}"><td class="mono mut">{_fmt_ts(a["ts"])}</td>'
            f'<td><span class="lv" style="color:{color};border:1px solid {color}33;'
            f'background:{color}14">{e(lv)}</span></td>'
            f'<td class="mut mono">{e(a["source"])}</td>'
            f'<td>{title}{detail}</td></tr>'
        )

    reg_rows = []
    for r in data["registries"]:
        badge = ('<span class="tag new">未登记</span>' if r["is_new"]
                 else f'<span class="tag">{e(r["known"])}</span>')
        reg_rows.append(
            f'<tr><td class="mono mut">{e(r["event"])}</td>'
            f'<td class="mut">{e(r["label"])}</td>'
            f'<td class="mono">{e(r["value"])}</td><td>{badge}</td></tr>'
        )

    ctx_rows = "".join(
        f'<tr><td class="mono mut">{e(c["name"])}</td>'
        f'<td class="mono">{e(c["address"])}</td>'
        f'<td class="mono mut">{e(c["impl"]) or "—"}</td>'
        f'<td class="mono mut">{e(c["code"])}…</td></tr>'
        for c in data["contracts"]
    )
    doc_rows = "".join(
        f'<tr><td>{e(d["name"])}</td><td class="mono mut">{e(d["mode"])}</td>'
        f'<td class="mut mono">{e(d["url"])}</td>'
        f'<td>{"✅" if d["baseline"] else "⏳"}</td></tr>'
        for d in data["docs"]
    )
    repo_rows = "".join(
        f'<tr><td class="mono">{e(r["repo"])}</td><td class="mut">{e(r["branch"])}</td>'
        f'<td>{"✅" if r["baseline"] else "⏳"}</td></tr>'
        for r in data["repos"]
    )
    chain_rows = "".join(
        f'<tr><td class="mono">{e(c["chain"])}</td>'
        f'<td class="mono">{e(str(c["cursor"] or "—"))}</td>'
        f'<td class="mut">{c["ids"]} 个合约</td></tr>'
        for c in data["chains"]
    )
    ev_rows = "".join(
        f'<tr><td class="mono">{e(x["name"])}</td>'
        f'<td class="mono mut">{e(x["signature"])}</td></tr>'
        for x in data["events_watched"]
    )

    gen = _fmt_ts(data["generated_at"], "%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FLAP / four.meme 新模式雷达</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header>
  <h1>FLAP / four.meme 新模式雷达</h1>
  <span class="sub">生成于 {e(gen)} · 只读快照</span>
</header>
<div class="sub">盯的是「平台新玩法」而不是币价：仓库代码 · 文档 · 合约升级 · 链上枚举首见</div>

<div class="grid">
  {card(o["events"], "告警总数（最多 300 条）")}
  {card(o["crit"], "其中高危")}
  {card(o["last24"], "最近 24 小时")}
  {card(o["contracts"], "监控合约")}
  {card(o["docs"], "文档目标")}
  {card(o["repos"], "代码仓库")}
  {card(o["outbox"], "待重试推送")}
</div>

<h2>告警流水</h2>
<div class="filters">
  <button class="on" onclick="flt('all',this)">全部</button>
  <button onclick="flt('crit',this)">高危</button>
  <button onclick="flt('warn',this)">注意</button>
  <button onclick="flt('info',this)">信息</button>
</div>
<table id="alerts"><thead><tr><th style="width:86px">时间</th>
<th style="width:64px">级别</th><th style="width:170px">来源</th><th>内容</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="4" class="mut">还没有告警</td></tr>'}</tbody></table>

<h2>链上模式编号注册表</h2>
<div class="sub" style="margin-bottom:8px">出现「未登记」的取值 = 一个新玩法第一次上链。</div>
<table><thead><tr><th>事件</th><th>字段</th><th>取值</th><th>状态</th></tr></thead>
<tbody>{''.join(reg_rows) or '<tr><td colspan="4" class="mut">还没有数据</td></tr>'}</tbody></table>

<h2>监控目标</h2>
<table><thead><tr><th>合约</th><th>地址</th><th>实现地址</th><th>字节码</th></tr></thead>
<tbody>{ctx_rows}</tbody></table>

<h2>文档与仓库</h2>
<table><thead><tr><th>文档目标</th><th>抓取方式</th><th>地址</th><th>基线</th></tr></thead>
<tbody>{doc_rows}</tbody></table>
<table style="margin-top:8px"><thead><tr><th>仓库</th><th>分支</th><th>基线</th></tr></thead>
<tbody>{repo_rows}</tbody></table>

<h2>链与事件</h2>
<table><thead><tr><th>链</th><th>已扫到区块</th><th>范围</th></tr></thead>
<tbody>{chain_rows}</tbody></table>
<table style="margin-top:8px"><thead><tr><th>监听事件</th><th>签名</th></tr></thead>
<tbody>{ev_rows}</tbody></table>

<footer>
本页由 <span class="mono">python -m radar.main --export-html</span> 生成，数据来自 SQLite 快照。
告警去重基于内容哈希：同样的信号不会重复刷屏，未见过的新取值一定会出现。
</footer>
</div>
<script>{JS}</script>
</body></html>"""


def export(cfg, state, html_path=None, json_path=None):
    data = collect(cfg, state)
    if html_path:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(data))
    if json_path:
        write_json(data, json_path)
    return data
