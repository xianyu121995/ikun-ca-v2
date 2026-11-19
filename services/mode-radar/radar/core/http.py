"""Tiny stdlib HTTP client: retries, timeouts, browser-ish UA, optional proxy."""

from __future__ import annotations

import gzip
import io
import json
import random
import time
import urllib.error
import urllib.request

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class HttpError(RuntimeError):
    pass


def _header_map(headers):
    out = {}
    if not headers:
        return out
    for key in headers.keys():
        out[key.lower()] = headers.get(key)
    return out


class Http:
    def __init__(self, timeout=20, retries=3, user_agent=DEFAULT_UA, proxy=None):
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        if proxy:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            self._opener = urllib.request.build_opener(handler)
        else:
            self._opener = urllib.request.build_opener()

    def request(self, method, url, body=None, headers=None, timeout=None):
        hdrs = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "application/json;q=0.8,*/*;q=0.7",
            "Accept-Encoding": "gzip",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }
        if headers:
            hdrs.update(headers)
        raw = None
        if body is not None:
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")

        last = None
        for attempt in range(self.retries):
            req = urllib.request.Request(url, data=raw, headers=hdrs, method=method)
            try:
                with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                    data = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                    return resp.status, data
            except urllib.error.HTTPError as e:
                last = HttpError(f"HTTP {e.code} for {url}")
                # 4xx (except 429) will not fix themselves
                if 400 <= e.code < 500 and e.code != 429:
                    raise last
            except Exception as e:  # noqa: BLE001 - network layer, retry everything
                last = HttpError(f"{type(e).__name__}: {e} ({url})")
            if attempt < self.retries - 1:
                time.sleep(min(8, 1.5 * (2 ** attempt)) * (0.7 + random.random() * 0.6))
        raise last

    def conditional_get(self, url, headers=None, timeout=None):
        """One GET. Returns (status, headers, body). 304 and 4xx are results, not retries."""
        hdrs = {
            "User-Agent": self.user_agent,
            "Accept": "application/vnd.github+json, application/json;q=0.8, text/plain;q=0.7",
            "Accept-Encoding": "gzip",
        }
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return resp.status, _header_map(resp.headers), data
        except urllib.error.HTTPError as e:
            data = e.read() if e.fp else b""
            if e.headers and e.headers.get("Content-Encoding") == "gzip" and data:
                try:
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                except OSError:
                    pass
            return e.code, _header_map(e.headers), data

    def get_text(self, url, **kw):
        status, data = self.request("GET", url, **kw)
        return data.decode("utf-8", "replace")

    def get_json(self, url, **kw):
        status, data = self.request("GET", url, **kw)
        try:
            return json.loads(data.decode("utf-8", "replace"))
        except json.JSONDecodeError as e:
            raise HttpError(f"bad json from {url}: {e}") from e

    def post_json(self, url, payload, **kw):
        status, data = self.request("POST", url, body=payload, **kw)
        text = data.decode("utf-8", "replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text, "status": status}
