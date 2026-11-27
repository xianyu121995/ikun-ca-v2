"""Official MagicBlock Blitz series hub. Past editions are not invented from recap posts."""

from urllib.parse import urlsplit


HUB = "https://build.magicblock.app/"
MAGICBLOCK_HUB = HUB.rstrip("/")


def discover_magicblock(timeout=15):
    return [{
        "name": "MagicBlock Blitz",
        "url": HUB,
        "kind": "magicblock",
        "chain": "SOL",
        "event_status": "scheduled",
    }]


def fetch_magicblock(url, fetch, timeout=15):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "build.magicblock.app":
        raise ValueError("MagicBlock 来源必须是 build.magicblock.app")
    html = fetch(HUB, timeout)
    if "MagicBlock" not in html or "Blitz" not in html:
        raise ValueError("MagicBlock 系列页没有公开的 Blitz 标识")
    closed = "No open events to submit to right now" in html
    return {
        "name": "MagicBlock Blitz",
        "chain": "SOL",
        "event_status": "scheduled" if closed else "active",
        "submission_status": "not_published" if closed else "unverified",
        "winner_status": "not_published",
        "submissions": [],
        "winners": [],
        "schedule": [],
        "links": [],
        "event_website": HUB,
        "summary": "MagicBlock 官方 Blitz 系列入口。页面没有公开在办的一届，也没有公开作品或获奖名单。" if closed else "MagicBlock 官方 Blitz 系列入口。",
        "scope_note": "MagicBlock 官方系列入口，不是从回顾文章补出来的往届名单。",
    }
