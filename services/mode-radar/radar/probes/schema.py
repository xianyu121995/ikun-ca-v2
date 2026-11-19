"""API / frontend-JSON schema watcher.

Poll a JSON endpoint (four.meme or flap web API) and diff its shape:
  * a new field or a new enum value usually means a new launch mode or option
    that the frontend already knows about.
Configure `enum_paths` with dotted paths whose *value set* must be tracked.
"""

from __future__ import annotations

from .base import Probe, Signal

MAX_NODES = 8000


def flatten(obj, prefix="", depth=0, out=None):
    """{'a.b[].c': type_name} walking nested JSON, capped in size."""
    if out is None:
        out = {}
    if len(out) >= MAX_NODES or depth > 7:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("data", "rows") and isinstance(v, list):
                pass
            flatten(v, f"{prefix}.{k}" if prefix else str(k), depth + 1, out)
    elif isinstance(obj, list):
        if obj:
            flatten(obj[0], f"{prefix}[]", depth + 1, out)
    else:
        out[prefix] = type(obj).__name__
    return out


def walk_path(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            if not cur:
                return None
            cur = cur[0]
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


class SchemaProbe(Probe):
    name = "schema"
    default_interval = 900

    def run(self, ctx):
        signals = []
        for target in self.cfg.get("targets", []):
            if not target.get("enabled", True):
                continue
            try:
                signals += self._check(ctx, target)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"[schema] {target.get('name')} failed: {e}")
        return signals

    def _check(self, ctx, target):
        name = target["name"]
        source = f"schema:{name}"
        payload = ctx.http.get_json(target["url"], headers=target.get("headers"))

        shape = flatten(payload)
        baseline_key = f"schema_baseline:{name}"
        seeded = ctx.state.get_meta(baseline_key)

        signals = []
        new_paths = []
        for path, typ in shape.items():
            state, _ = ctx.state.observe(source, f"path:{path}", typ)
            if state == "new":
                new_paths.append((path, typ))

        # enum-style value tracking
        enum_paths = target.get("enum_paths") or []
        for path in enum_paths:
            value = walk_path(payload, path)
            if value is None:
                continue
            state, _ = ctx.state.observe(source, f"enum:{path}", value)
            if state == "new" and seeded:
                signals.append(Signal(
                    source=source, key=f"enum:{path}={value}", kind="new", level="crit",
                    title=f"{name}: 新的 {path} = {value}",
                    detail="接口里出现了一个此前没见过的取值，极可能对应新模式。",
                    url=target["url"], payload={"path": path, "value": value},
                    fingerprint=f"{path}={value}",
                ))

        if not seeded:
            ctx.state.set_meta(baseline_key, 1)
            return signals + [Signal(
                source=source, key="baseline", kind="new", level="info",
                title=f"已建立接口基线：{name}（{len(shape)} 个字段）",
                detail="首次运行，仅记录结构。", url=target["url"],
            )]

        for path, typ in new_paths:
            if path.endswith("[]") or not path:
                continue
            level = "warn" if any(
                k in path.lower() for k in ("mode", "type", "protocol", "launch", "version", "category")
            ) else "info"
            signals.append(Signal(
                source=source, key=f"path:{path}", kind="new", level=level,
                title=f"{name}: 接口新增字段 {path} ({typ})",
                detail="接口结构变了，前端可能已上线新功能。",
                url=target["url"], payload={"path": path, "type": typ}, fingerprint=path,
            ))
        return signals
