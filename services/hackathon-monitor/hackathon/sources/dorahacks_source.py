"""Conservative fallback for publicly rendered DoraHacks BUIDL links."""

from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.href = None
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.text = []

    def handle_data(self, text):
        if self.href:
            self.text.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join("".join(self.text).split())))
            self.href = None


def read_dorahacks(url, get):
    overview = Links(get(url)).links
    path = urlsplit(url).path
    result = {"submission_status": "unverified", "winner_status": "unverified"}
    for label, kind, field in (
        ({"buidls", "projects", "submissions"}, "submission", "submissions"),
        ({"winner", "winners"}, "winner", "winners"),
    ):
        tabs = [urljoin(url, href) for href, name in overview if name.casefold() in label]
        tab = next((link for link in tabs
                    if urlsplit(link).hostname in {"dorahacks.io", "www.dorahacks.io"}
                    and urlsplit(link).path.startswith(path + "/")), None)
        if not tab:
            continue
        try:
            cards = Links(get(tab)).links
        except (OSError, ValueError) as error:
            result[kind + "_status"] = "error"
            result[kind + "_error"] = str(error)
            continue
        items = {}
        for href, name in cards:
            link = urljoin(tab, href)
            parts = urlsplit(link)
            match = re.fullmatch(r"/buidl/(\d+)/?", parts.path)
            if parts.hostname in {"dorahacks.io", "www.dorahacks.io"} and match and name:
                if name.casefold() not in {"view", "details", "view project", "learn more"}:
                    items.setdefault(match[1], {"id": match[1], "name": name, "url": link})
        if items:
            result[field] = list(items.values())
            result[kind + "_status"] = "partial"
    return result

