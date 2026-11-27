"""Public HTTP only. No authenticated Binance sessions and no paid APIs."""

from __future__ import annotations

import gzip
import io
import time
import urllib.error
import urllib.request

UA = "ikun-hackathon-monitor/1.0 (+https://ikun.ca; official-public-sources)"


class FetchError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class HttpClient:
    def __init__(self, timeout: int = 25, retries: int = 3, gap: float = 0.8):
        self.timeout = timeout
        self.retries = retries
        self.gap = gap
        self._last = 0.0
        self._opener = urllib.request.build_opener()

    def fetch(self, url: str, headers: dict | None = None) -> tuple[int, bytes]:
        wait = self.gap - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        hdrs = {
            "User-Agent": UA,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if headers:
            hdrs.update(headers)
        last = FetchError(f"请求失败 {url}")
        for attempt in range(self.retries):
            request = urllib.request.Request(url, headers=hdrs, method="GET")
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        payload = gzip.GzipFile(fileobj=io.BytesIO(payload)).read()
                    return response.status, payload
            except urllib.error.HTTPError as error:
                last = FetchError(f"HTTP {error.code}", error.code)
                if 400 <= error.code < 500 and error.code != 429:
                    raise last
            except Exception as error:  # noqa: BLE001 - network boundary
                last = FetchError(f"{type(error).__name__}")
            if attempt < self.retries - 1:
                time.sleep(min(8, 1.5 * (2 ** attempt)))
        raise last
