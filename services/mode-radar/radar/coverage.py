"""Honest coverage labels. Do not describe partial config as a complete monitor."""

from __future__ import annotations


def _chain(cfg, name):
    return ((cfg.get("probes") or {}).get("onchain") or {}).get("chains", {}).get(name) or {}


def chain_mode(ccfg) -> str:
    """configured | disabled | unconfigured. Never treats HTTP RPC as configured."""
    if not ccfg or not ccfg.get("enabled", True):
        return "disabled"
    wss = (ccfg.get("wss") or "").strip()
    if not wss:
        return "unconfigured"
    if not wss.startswith("wss://"):
        return "unconfigured"
    contracts = ccfg.get("contracts") or []
    events = ccfg.get("events") or []
    if not contracts and not events:
        return "unconfigured"
    return "configured"


def coverage_report(cfg, state=None) -> list[dict]:
    probes = cfg.get("probes") or {}
    discover = probes.get("discover") or {}
    owners = [o.get("login") for o in (discover.get("owners") or []) if o.get("enabled", True) and o.get("login")]
    missing = [item.get("project") for item in (discover.get("unconfigured") or [])]
    docs = [t.get("name") for t in (probes.get("docs") or {}).get("targets") or [] if t.get("enabled", True)]
    repos = [r.get("repo") for r in (probes.get("github") or {}).get("repos") or [] if r.get("enabled", True)]
    bsc = _chain(cfg, "bsc")
    four = _chain(cfg, "fourmeme")
    bsc_mode = chain_mode(bsc)
    four_mode = chain_mode(four)
    log_addresses = {a.lower() for a in (bsc.get("log_addresses") or [])}
    four_contracts = [
        c for c in (bsc.get("contracts") or [])
        if "fourmeme" in (c.get("name") or "").lower()
    ]
    four_in_logs = [
        c for c in four_contracts if (c.get("address") or "").lower() in log_addresses
    ]
    flap_events = [e.get("name") for e in (bsc.get("events") or [])]
    return [
        {
            "id": "flap-docs",
            "project": "FLAP",
            "kind": "文档",
            "state": "configured" if "flap" in docs else "unconfigured",
            "summary": "docs.flap.sh 侧边栏与部署地址页，限速定时检查。首次只建基线。",
            "limit": "抓的是公开文档目录，不是链上成交。",
        },
        {
            "id": "flap-github",
            "project": "FLAP",
            "kind": "仓库",
            "state": "configured" if "flap-sh" in owners else "unconfigured",
            "summary": "已核实官方 GitHub owner：flap-sh。每小时列出其公开仓库，发现新仓库后站内提醒。",
            "limit": "依据是 docs.flap.sh 开发页上的 github.com/flap-sh 链接。不读取、不执行仓库内容。无 token 时和文件树探针共用每小时 60 次 API 额度，所以不是秒级。four.meme 社区仓库不算 FLAP。",
        },
        {
            "id": "flap-identity",
            "project": "FLAP",
            "kind": "合约身份",
            "state": bsc_mode if bsc_mode != "configured" else "configured",
            "summary": "BSC 上附件列出的 FLAP Portal / Vault / Dock。只在 WSS newHeads 推动下读实现槽和字节码。",
            "limit": "地址来自附件配置，本仓库没有把它核对成官方全集。未配置 WSS 时这条链禁用，不用 HTTP 轮询代替。",
        },
        {
            "id": "flap-events",
            "project": "FLAP",
            "kind": "链上事件",
            "state": "unconfigured" if bsc_mode != "configured" else "configured",
            "summary": "WSS logs 订阅：" + ("、".join(flap_events) if flap_events else "无事件"),
            "limit": "只看 log_addresses 里的已知地址。新部署到全新地址的协议不在订阅里。已知取值来自附件的 known 表，首跑写入基线，不把这些历史取值报成新变化。",
        },
        {
            "id": "four-docs",
            "project": "four.meme",
            "kind": "文档",
            "state": "configured" if "fourmeme" in docs else "unconfigured",
            "summary": "GitBook llms.txt 与集成指南里的地址表。限速定时检查，首跑只建基线。",
            "limit": "文档新增不等于链上事件已经覆盖。",
        },
        {
            "id": "four-github",
            "project": "four.meme",
            "kind": "仓库",
            "state": "configured" if repos else "unconfigured",
            "summary": ("仍只跟踪社区文档仓库文件树：" + "、".join(repos)) if repos else "未配置仓库",
            "limit": "官方 owner 未配置：" + ("、".join(missing) if missing else "没有已核实的 four.meme GitHub 组织") + "。不把 four-meme-community 的新仓库当成官方发现，也不做全网关键词搜索。",
        },
        {
            "id": "four-identity",
            "project": "four.meme",
            "kind": "合约身份",
            "state": "partial" if four_contracts and bsc_mode == "configured" else ("disabled" if bsc_mode == "disabled" else "unconfigured"),
            "summary": f"BSC 合约表里有 {len(four_contracts)} 个名字含 fourmeme 的地址，只做实现槽/字节码。",
            "limit": "不是完整 four.meme。名为 fourmeme 的独立链在配置里是空 TODO，默认关闭。这些地址没有在本仓库用官方材料重新取证。",
        },
        {
            "id": "four-events",
            "project": "four.meme",
            "kind": "链上事件",
            "state": "configured" if four_in_logs and four_mode == "configured" else "unconfigured",
            "summary": "four.meme 事件枚举未接入。" if not four_in_logs else "已订阅 four.meme 地址上的日志。",
            "limit": "log_addresses 不含 TokenManager；也没有 four.meme 事件签名。不能宣称已覆盖 four.meme 新模式上链。空链 fourmeme 保持禁用，缺签名就不猜。",
        },
    ]
