"""Decide whether an official page is a hackathon, a related event, or noise."""

from __future__ import annotations

import re

_HACKATHON = re.compile(r"hackathon|黑客松|(?<![a-z])hack(?![a-z])", re.I)
_RELATED = re.compile(
    r"blockchain week|accelerator|\bmvb\b|trading competition|交易大赛|campaign|黑客松目录",
    re.I,
)


def mentions_hackathon(*parts: str) -> bool:
    return any(_HACKATHON.search(part or "") for part in parts)


def classify_text(*parts: str) -> tuple[str, str] | None:
    """Return (hackathon|related, reason) or None when the text is not this monitor's subject."""
    blob = "\n".join(part for part in parts if part)
    if mentions_hackathon(blob):
        return "hackathon", "标题或摘要使用了黑客松 / hackathon / hack。"
    if _RELATED.search(blob):
        return "related", "官方文本把它称作周会、加速器、交易赛或 campaign，而不是黑客松。"
    return None


def classify_index_program(title: str, description: str = "") -> tuple[str, str]:
    """Everything on the official hackathon index is in scope. The label follows the page's own words."""
    found = classify_text(title, description)
    if found and found[0] == "hackathon":
        return found
    return "related", "出现在 BNB Chain 官方黑客松目录中，但标题没有称它为黑客松。"


def announcement_in_scope(title: str) -> bool:
    """Recent Binance activity feeds are mostly trading campaigns. Only hackathon wording is ingested."""
    return mentions_hackathon(title)


_WINNERS = re.compile(
    r"^(meet the winners|winners of|获奖名单|获奖项目|入选名单|shortlisted)\b",
    re.I,
)


def blog_role(title: str, excerpt: str) -> str | None:
    """event, results, or None. Results posts attach to a hackathon instead of becoming a second event."""
    if not mentions_hackathon(title, excerpt):
        return None
    if _WINNERS.search((title or "").strip()):
        return "results"
    return "event"
