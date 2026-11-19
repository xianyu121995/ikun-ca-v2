"""Alert fan-out: console, generic webhook (Feishu / WeCom / Discord / Slack), Telegram.

Delivery is best-effort but not lossy: when every configured channel fails the
batch is written to the outbox table and retried on the next loop iteration.
"""

from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace

LEVEL_ICON = {"info": "ℹ️", "warn": "⚠️", "crit": "🚨"}
LEVEL_ORDER = {"info": 0, "warn": 1, "crit": 2}


def _safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, "replace").decode(enc, "replace"))


def _fmt_line(sig):
    icon = LEVEL_ICON.get(sig.level, "•")
    head = f"{icon} [{sig.source}] {sig.title}"
    body = f"\n    {sig.detail}" if sig.detail else ""
    link = f"\n    {sig.url}" if sig.url else ""
    return head + body + link


def format_batch(signals, title="模式雷达"):
    crit = sum(1 for s in signals if s.level == "crit")
    head = f"**{title}**: {len(signals)} 条新信号" + (f"（{crit} 条高危）" if crit else "")
    return head + "\n\n" + "\n".join(_fmt_line(s) for s in signals)


class Notifier:
    def __init__(self, cfg, http, state=None):
        self.cfg = cfg or {}
        self.http = http
        self.state = state
        self.min_level = self.cfg.get("min_level", "info")

    def _passes(self, sig):
        return LEVEL_ORDER.get(sig.level, 0) >= LEVEL_ORDER.get(self.min_level, 0)

    def has_external(self):
        if not self.cfg.get("allow_external"):
            return False
        hook = self.cfg.get("webhook_url") or ""
        return (hook.startswith("https://")) or bool(
            (self.cfg.get("telegram") or {}).get("token")
            and (self.cfg.get("telegram") or {}).get("chat_id")
        )

    def send(self, signals):
        """Push a batch. Returns True when nothing needs to be retried."""
        signals = [s for s in signals if self._passes(s)]
        if not signals:
            return True

        if self.cfg.get("console", True):
            _safe_print("-" * 72)
            for s in signals:
                _safe_print(_fmt_line(s))
            _safe_print("-" * 72)
            sys.stdout.flush()

        text = format_batch(signals)
        errors = []

        hook = self.cfg.get("webhook_url", "") if self.cfg.get("allow_external") else ""
        if hook and not str(hook).startswith("https://"):
            errors.append("webhook: https required")
            hook = ""
        if hook:
            try:
                self._webhook(hook, text, signals)
            except Exception as e:  # noqa: BLE001 - alerting must never kill the loop
                errors.append(f"webhook: {e}")
                _safe_print(f"[notify] webhook failed: {e}")

        tg = (self.cfg.get("telegram") or {}) if self.cfg.get("allow_external") else {}
        if tg.get("token") and tg.get("chat_id"):
            try:
                self._telegram(tg["token"], tg["chat_id"], text)
            except Exception as e:  # noqa: BLE001
                errors.append(f"telegram: {e}")
                _safe_print(f"[notify] telegram failed: {e}")

        if errors and self.state is not None:
            # every external channel failed -> keep it, retry later
            try:
                self.state.queue_alert([s.__dict__ for s in signals])
                _safe_print(f"[notify] 已入 outbox 待重试（{len(signals)} 条）: {errors}")
            except Exception as e:  # noqa: BLE001
                _safe_print(f"[notify] outbox 写入失败: {e}")
        return not errors

    def flush(self, limit=10):
        """Retry queued alerts. Returns how many batches were delivered."""
        if self.state is None or not self.has_external():
            return 0
        done = 0
        for row in self.state.pending_alerts(limit):
            try:
                batch = json.loads(row["payload"])
            except json.JSONDecodeError:
                self.state.drop_alert(row["id"])
                continue
            sigs = [SimpleNamespace(**d) for d in batch]
            if self.send(sigs):
                self.state.drop_alert(row["id"])
                done += 1
            else:
                self.state.bump_alert(row["id"], "retry failed")
                break  # channel is still down, don't burn the rest
        return done

    # ------------------------------------------------------------------
    def _webhook(self, url, text, signals):
        if "open.feishu.cn" in url:
            payload = {"msg_type": "text", "content": {"text": text.replace("**", "")}}
        elif "qyapi.weixin.qq.com" in url:
            payload = {"msgtype": "markdown", "markdown": {"content": text}}
        elif "discord.com" in url or "discordapp.com" in url:
            payload = {"content": text[:1900]}
        elif "hooks.slack.com" in url:
            payload = {"text": text.replace("**", "*")}
        else:
            payload = {"text": text, "signals": [
                {"source": s.source, "key": s.key, "kind": s.kind, "level": s.level,
                 "title": s.title, "detail": s.detail, "url": s.url}
                for s in signals
            ]}
        self.http.post_json(url, payload)

    def _telegram(self, token, chat_id, text):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.http.post_json(
            url,
            {
                "chat_id": chat_id,
                "text": text.replace("**", "*")[:4000],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
