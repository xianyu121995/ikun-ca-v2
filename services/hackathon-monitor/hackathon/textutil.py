"""Small HTML / rich-text helpers. Raw pages are not stored."""

from __future__ import annotations

import html
import json
import re


def strip_tags(value: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", value or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>|</li>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def collapse(value: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def next_data(page: str) -> dict | None:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def article_fragment(page: str) -> str:
    """Slice a BNB Chain blog article out of the full document."""
    start = page.find("<h1")
    if start < 0:
        return page
    end = page.find(">Share<", start)
    if end < 0:
        end = min(len(page), start + 80000)
    return page[start:end]


def html_tables(fragment: str) -> list[list[list[str]]]:
    tables = []
    for table in re.findall(r"(?is)<table[^>]*>.*?</table>", fragment or ""):
        rows = []
        for row in re.findall(r"(?is)<tr[^>]*>.*?</tr>", table):
            cells = [collapse(strip_tags(cell), 240) for cell in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", row)]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def rich_text(body) -> tuple[str, list[tuple[str, str]]]:
    """Binance article bodies are a JSON tree, sometimes double-encoded. Returns text and (label, href)."""
    node = body
    if isinstance(node, str):
        stripped = node.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                node = json.loads(stripped)
            except json.JSONDecodeError:
                return strip_tags(node), _html_links(node)
        else:
            return strip_tags(node), _html_links(node)
    texts: list[str] = []
    links: list[tuple[str, str]] = []
    recent: list[str] = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("node") == "text" and isinstance(value.get("text"), str):
                texts.append(value["text"])
                recent.append(value["text"])
                del recent[:-8]
            href = None
            attr = value.get("attr")
            if isinstance(attr, dict):
                href = attr.get("href")
            if isinstance(href, str) and href.startswith("http"):
                label = _node_text(value.get("child"))
                context = " ".join(recent[-4:] + ([label] if label else []))
                links.append((collapse(context, 180), href))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return "\n".join(texts), links


def _node_text(value) -> str:
    parts: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("node") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return collapse(" ".join(parts), 120)


def _html_links(value: str) -> list[tuple[str, str]]:
    found = []
    for href in re.findall(r'(?i)href="(https?://[^"]+)"', value or ""):
        found.append(("", html.unescape(href)))
    return found
