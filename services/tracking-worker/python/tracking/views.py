import base64
import hashlib
import json
import math
import re
import time

from .commands import activity
from .protocol import SCOPE, UUID4, DomainError, canonical, utc


def subscription(store, row, *, db=None, fresh_seconds=45, projection=None):
    if db is None:
        with store.connect() as con:
            return subscription(store, row, db=con, fresh_seconds=fresh_seconds)
    runtime = projection[0] if projection else dict(db.execute("SELECT * FROM runtime WHERE id=1").fetchone())
    connected = bool(
        runtime["heartbeat"]
        and time.time() - runtime["heartbeat"] < 10
        and runtime["connection"] == "connected"
        and runtime["pong_at"]
        and time.time() - runtime["pong_at"] < 30
    )
    fresh = bool(row["observed_at"] and time.time() - row["observed_at"] < fresh_seconds)
    observed = (
        {"active": "running", "absent": "absent"}.get(row["remote_state"], "unknown") if fresh else "unknown"
    )
    cmd = projection[1].get(row['active_command_id']) if projection else db.execute("SELECT state FROM commands WHERE command_id=?", (row["active_command_id"],)).fetchone()
    last = projection[2].get(row['subscription_id']) if projection else db.execute(
        "SELECT MAX(created_at) FROM tweets WHERE subscription_id=?", (row["subscription_id"],)
    ).fetchone()[0]
    return {
        "subscription_id": row["subscription_id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "x_user_id": row["x_user_id"],
        "x_handle": row["handle"],
        "notes": row["notes"],
        "revision": row["revision"],
        "desired_state": row["desired"],
        "observed_state": observed,
        "operation_state": cmd[0] if cmd else "unknown",
        "error_code": row["error"],
        "connection": "connected"
        if connected
        else "connecting"
        if runtime["connection"] == "connecting"
        and runtime["heartbeat"]
        and time.time() - runtime["heartbeat"] < 10
        else "unconfigured"
        if runtime["error"] == "remote_not_configured"
        else "disconnected",
        "last_tweet_at": utc(last),
        "created_at": utc(row["created_at"]),
        "updated_at": utc(row["updated_at"]),
    }


def page(store, kind, query, *, fresh_seconds=45):
    allowed = (
        {"q", "include_removed", "cursor", "limit"}
        if kind == "subscriptions"
        else {"project_id", "subscription_id", "cursor", "limit"}
    )
    if query.keys() - allowed:
        raise DomainError(422, "VALIDATION_ERROR", "unsupported query fields")
    try:
        limit = int(query.get("limit", "50"))
        maximum = 1000 if kind == 'subscriptions' else 100
        if not 1 <= limit <= maximum:
            raise ValueError()
    except (ValueError, TypeError):
        raise DomainError(422, "VALIDATION_ERROR", "limit out of range") from None
    bound = hashlib.sha256(
        canonical([SCOPE, kind, {k: v for k, v in query.items() if k not in ("cursor", "limit")}]).encode()
    ).hexdigest()
    after = None
    if "cursor" in query:
        try:
            raw = query["cursor"]
            decoded = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            if set(decoded) != {"scope", "key"} or decoded["scope"] != bound:
                raise ValueError()
            after = decoded["key"]
            if (
                not isinstance(after, list)
                or len(after) != 2
                or type(after[0]) not in (int, float)
                or not math.isfinite(after[0])
            ):
                raise ValueError()
            if kind == "subscriptions":
                if not isinstance(after[1], str) or not re.fullmatch("sub_" + UUID4, after[1]):
                    raise ValueError()
            elif type(after[1]) is not int or after[1] < 1:
                raise ValueError()
            if (
                not isinstance(after, list)
                or len(after) != 2
                or not isinstance(after[0], (int, float))
                or not isinstance(after[1], (int, str))
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise DomainError(422, "VALIDATION_ERROR", "invalid or mismatched cursor") from None
    for field, prefix in [("project_id", "prj_"), ("subscription_id", "sub_")]:
        if field in query and not re.fullmatch(prefix + UUID4, query[field]):
            raise DomainError(422, "VALIDATION_ERROR", "invalid resource filter")
    with store.connect() as db:
        from .retention import retention_now

        if kind == 'subscriptions':
            db.execute('BEGIN')  # Read-only list: no retention clock write/fsync on every request.
            now = 0
        else:
            now = retention_now(db)
        if kind == "subscriptions":
            if query.get("include_removed", "false") not in ("true", "false"):
                raise DomainError(422, "VALIDATION_ERROR", "invalid include_removed")
            rows = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY updated_at,subscription_id")]
            rows = [
                r
                for r in rows
                if (
                    query.get("include_removed") == "true"
                    or r["desired"] != "removed"
                    or r["remote_state"] != "absent"
                )
                and query.get("q", "").lower() in (r["name"] + " " + r["handle"] + " " + r["notes"]).lower()
            ]

            def key(r):
                return [r["updated_at"], r["subscription_id"]]

            if after:
                rows = [r for r in rows if key(r) > after]
            selected=rows[:limit]
            runtime=dict(db.execute("SELECT * FROM runtime WHERE id=1").fetchone())
            # Three bulk reads replace three per-row queries, within the same read snapshot.
            command_ids=[r['active_command_id'] for r in selected if r['active_command_id']]
            commands={r[0]:(r[1],) for r in db.execute('SELECT command_id,state FROM commands WHERE command_id IN ('+','.join('?' for _ in command_ids)+')',command_ids)} if command_ids else {}
            ids=[r['subscription_id'] for r in selected]
            last={r[0]:r[1] for r in db.execute('SELECT subscription_id,MAX(created_at) FROM tweets WHERE subscription_id IN ('+','.join('?' for _ in ids)+') GROUP BY subscription_id',ids)} if ids else {}
            items = [subscription(store,r,db=db,fresh_seconds=fresh_seconds,projection=(runtime,commands,last)) for r in selected]
        else:
            descending = kind == "latest"
            clauses = ["t.expires_at_ms>?", "t.tweet_kind IN ('original','quote')", "t.author_verified=1"]
            args = [now]
            for field in ("project_id", "subscription_id"):
                if field in query:
                    clauses.append("t." + field + "=?")
                    args.append(query[field])
            if after:
                op = "<" if descending else ">"
                clauses.append(f"(t.received_at,t.seq){op}(?,?)")
                args += after
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id)"
                    + (" WHERE " + " AND ".join(clauses) if clauses else "")
                    + " ORDER BY t.received_at "
                    + ("DESC" if descending else "ASC")
                    + ",t.seq "
                    + ("DESC" if descending else "ASC")
                    + " LIMIT ?",
                    (*args, limit + 1),
                )
            ]

            def key(r):
                return [r["received_at"], r["seq"]]

            items = [activity(r) for r in rows[:limit]]
        cursor = (
            base64.urlsafe_b64encode(canonical({"scope": bound, "key": key(rows[limit - 1])}).encode())
            .decode()
            .rstrip("=")
            if len(rows) > limit
            else None
        )
        return {"items": items, "next_cursor": cursor}
