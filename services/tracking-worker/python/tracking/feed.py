"""Versioned published feed, materialized ID snapshots and authenticated ordinal cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, StrictInt, field_validator

from .protocol import UUID4, DomainError, Principal, Strict, canonical
from .retention import retention_now

PROFILE = "published-v1"
POLICY = "product-decisions-v1.2"
NS = uuid.UUID("c018deb2-7ccf-5092-8112-b5c9f71d40be")


def activity_id(sub, tweet_id):
    return "act_" + str(uuid.uuid5(NS, json.dumps(["ikun-main", sub, tweet_id], separators=(",", ":"))))


from .translate import translation_for


def quote_for(db, tweet_id):
    row = db.execute("SELECT result FROM receipts WHERE key=?", ("tracking.quote.v1:" + tweet_id,)).fetchone()
    return json.loads(row[0]) if row else None


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value, *, query=False):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1," + ("3" if query else "9") + r"})?Z", value
    ):
        raise ValueError("UTC required")
    dt = datetime.fromisoformat(value)
    delta = dt - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


class Query(Strict):
    q: str = Field(max_length=120)
    ratings: list[Literal["S", "A", "B"]] = Field(min_length=1, max_length=3)
    subscription_id: str | None = Field(pattern="^sub_" + UUID4 + "$")
    from_at: str | None
    until_at: str | None

    @field_validator("q")
    @classmethod
    def normalize_q(cls, value):
        return unicodedata.normalize("NFKC", value).strip().casefold()

    @field_validator("ratings")
    @classmethod
    def normalize_ratings(cls, value):
        return [r for r in ("S", "A", "B") if r in value]

    @field_validator("from_at", "until_at")
    @classmethod
    def times(cls, value):
        return iso(parse_time(value, query=True)) if value is not None else None


def query_hash(query):
    value = query.model_dump()
    if (
        value["from_at"]
        and value["until_at"]
        and parse_time(value["from_at"]) >= parse_time(value["until_at"])
    ):
        raise DomainError(422, "VALIDATION_ERROR", "invalid time interval")
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class FeedRequest(Strict):
    schema_version: Literal[1]
    actor: Principal

    @field_validator("schema_version", mode="before")
    @classmethod
    def version(cls, value):
        if type(value) is not int:
            raise ValueError("invalid schema version")
        return value


class BasisRequest(FeedRequest):
    query_view_id: str | None = Field(default=None, pattern="^qv1_" + UUID4 + "$")
    profile: Literal["published-v1"]
    query: Query


class Rating(Strict):
    project_id: str = Field(pattern="^prj_" + UUID4 + "$")
    state: Literal["found", "missing"]
    rating: Literal["S", "A", "B", "C", "D"] | None
    revision: StrictInt | None = Field(ge=1)


class Ratings(Strict):
    contract: Literal["tracking-ratings-v1"]
    catalog_version: str | None = Field(min_length=1, max_length=128)
    checked_at: str
    items: list[Rating] = Field(max_length=10000)


class SnapshotRequest(FeedRequest):
    basis_id: str = Field(pattern="^fbs_" + UUID4 + "$")
    query_hash: str = Field(pattern="^[a-f0-9]{64}$")
    limit: StrictInt = Field(ge=1, le=100)
    ratings_snapshot: Ratings


class PageRequest(FeedRequest):
    query_view_id: str | None = Field(default=None, pattern="^qv1_" + UUID4 + "$")
    cursor: str = Field(min_length=1, max_length=4096)
    limit: StrictInt = Field(ge=1, le=100)
    verified_catalog_version: str | None = Field(min_length=1, max_length=128)


def actor_hash(actor):
    return hashlib.sha256(canonical(actor.model_dump()).encode()).hexdigest()


def visible_subscriptions(db):
    return [
        dict(r)
        for r in db.execute(
            "SELECT p.*, (p.desired='removed' AND p.remote_state='absent' AND COALESCE(c.state,'unknown')='succeeded') AS removal_complete FROM projects p LEFT JOIN commands c ON c.command_id=p.active_command_id WHERE NOT(p.desired='removed' AND p.remote_state='absent' AND COALESCE(c.state,'unknown')='succeeded') OR EXISTS (SELECT 1 FROM tweets t WHERE t.subscription_id=p.subscription_id AND t.expires_at_ms>?) ORDER BY p.subscription_id",
            (retention_now(db),)
        )
    ]


def folded(db, now):
    groups = {}
    for raw in db.execute(
        "SELECT t.*,l.first_received_at_ms,l.origin_subscription_id,l.state AS ledger_state FROM tweets t JOIN tweet_ledger l USING(tweet_id) WHERE t.expires_at_ms>? AND l.expires_at_ms>? AND l.state!='expired' AND t.author_verified=1 ORDER BY t.seq",
        (now, now),
    ):
        row = dict(raw)
        if row["origin_subscription_id"] != row["subscription_id"] or row["first_received_at_ms"] is None:
            continue
        aid = activity_id(row["subscription_id"], row["tweet_id"])
        previous = groups.get(aid)
        if previous:
            if not row["text"]:
                row["text"] = previous["text"]
            if row["created_at"] is None:
                row["created_at"] = previous["created_at"]
            elif previous["created_at"] is not None:
                row["created_at"] = min(row["created_at"], previous["created_at"])
        row["folded_id"] = aid
        row["sort_at_ms"] = (
            int(row["created_at"] * 1000) if row["created_at"] is not None else row["first_received_at_ms"]
        )
        groups[aid] = row
    return groups


def selected(row, sub, query):
    if query.subscription_id and query.subscription_id != row["subscription_id"]:
        return False
    if query.from_at and row["sort_at_ms"] < parse_time(query.from_at):
        return False
    if query.until_at and row["sort_at_ms"] >= parse_time(query.until_at):
        return False
    return (
        query.q
        in unicodedata.normalize(
            "NFKC", " ".join((sub["notes"], sub["name"], sub["handle"], row["text"]))
        ).casefold()
    )


def conflict(message="feed snapshot changed or expired"):
    return DomainError(409, "VERSION_CONFLICT", message)


def capacity(db, extra_bytes=0, *, reserve=True):
    count = db.execute(
        "SELECT (SELECT COUNT(*) FROM feed_bases)+(SELECT COUNT(*) FROM feed_snapshots)"
    ).fetchone()[0]
    size = sum(
        db.execute("SELECT COALESCE(SUM(length(CAST(" + expr + " AS BLOB))),0) FROM " + table).fetchone()[0]
        for table, expr in (
            ("feed_bases", "candidate_ids||subscription_ids||project_ids||query_json"),
            ("feed_snapshots", "ordered_ids||ratings_json||counts_json"),
        )
    )
    if (reserve and count >= 8) or size + extra_bytes > 64 * 1024 * 1024:
        raise DomainError(429, "RATE_LIMITED", "feed snapshot capacity reached")


def basis(store, request: BasisRequest):
    hashed = query_hash(request.query)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = retention_now(db)
        db.execute("DELETE FROM feed_bases WHERE expires_at_ms<=?", (now,))
        db.execute("DELETE FROM feed_snapshots WHERE expires_at_ms<=?", (now,))
        meta = db.execute("SELECT * FROM feed_meta WHERE singleton=1").fetchone()
        for table in ("feed_bases", "feed_snapshots"):
            db.execute(
                f"DELETE FROM {table} WHERE semantic_revision!=? OR snapshot_epoch!=?",
                (meta["semantic_revision"], meta["snapshot_epoch"]),
            )
        if request.query_view_id is not None:
            for table in ("feed_bases", "feed_snapshots"):
                db.execute(
                    f"DELETE FROM {table} WHERE actor_hash=? AND query_view_id=?",
                    (actor_hash(request.actor), request.query_view_id),
                )
        capacity(db)
        subs = visible_subscriptions(db)
        sub_map = {r["subscription_id"]: r for r in subs}
        rows = [
            r
            for r in folded(db, now).values()
            if r["subscription_id"] in sub_map and selected(r, sub_map[r["subscription_id"]], request.query)
        ]
        project_ids = sorted({r["project_id"] for r in subs} | {r["project_id"] for r in rows})
        if len(rows) > 100000 or len(project_ids) > 10000:
            raise DomainError(422, "VALIDATION_ERROR", "feed query exceeds complete-query limit")
        identifier = "fbs_" + str(uuid.uuid4())
        encoded = [
            canonical(request.query.model_dump()),
            canonical([r["folded_id"] for r in rows]),
            canonical(list(sub_map)),
            canonical(project_ids),
        ]
        capacity(db, sum(len(value.encode()) for value in encoded), reserve=False)
        db.execute(
            "INSERT INTO feed_bases(basis_id,actor_hash,query_hash,query_json,semantic_revision,snapshot_epoch,as_of_ms,expires_at_ms,prepared_until_ms,candidate_ids,subscription_ids,project_ids,query_view_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                actor_hash(request.actor),
                hashed,
                encoded[0],
                meta["semantic_revision"],
                meta["snapshot_epoch"],
                now,
                now + 60000,
                now + 15000,
                *encoded[1:],
                request.query_view_id,
            ),
        )
        db.execute("COMMIT")
        return {
            "basis_id": identifier,
            "as_of": iso(now),
            "expires_at": iso(now + 60000),
            "semantic_revision": meta["semantic_revision"],
            "project_ids": project_ids,
            "query_hash": hashed,
        }


def _check_snapshot(meta, row, now):
    if (
        row["expires_at_ms"] <= now
        or row["semantic_revision"] != meta["semantic_revision"]
        or row["snapshot_epoch"] != meta["snapshot_epoch"]
    ):
        raise conflict()


def _cursor(meta, row, offset):
    value = {
        "v": 1,
        "s": row["snapshot_id"],
        "a": row["actor_hash"],
        "q": row["query_hash"],
        "p": PROFILE,
        "r": row["semantic_revision"],
        "c": row["catalog_version"],
        "e": row["expires_at_ms"],
        "x": row["snapshot_epoch"],
        "n": offset,
    }
    if row["query_view_id"] is not None:
        value["w"] = row["query_view_id"]
    payload = canonical(value).encode()

    def encode(b):
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    return encode(payload) + "." + encode(hmac.new(meta["cursor_key"], payload, hashlib.sha256).digest())


def _decode(meta, value):
    try:
        parts = value.split(".")
        if len(parts) != 2 or any(not re.fullmatch("[A-Za-z0-9_-]+", p) for p in parts):
            raise ValueError()

        def decode(b):
            return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))

        payload, signature = map(decode, parts)
        if not hmac.compare_digest(signature, hmac.new(meta["cursor_key"], payload, hashlib.sha256).digest()):
            raise ValueError()
        result = json.loads(payload)
        if (
            set(result)
            not in (
                {"v", "s", "a", "q", "p", "r", "c", "e", "x", "n"},
                {"v", "s", "a", "q", "p", "r", "c", "e", "x", "n", "w"},
            )
            or result["v"] != 1
            or result["p"] != PROFILE
            or type(result["n"]) is not int
            or result["n"] < 0
        ):
            raise ValueError()
        result.setdefault("w", None)
        if result["w"] is not None and (
            not isinstance(result["w"], str) or not re.fullmatch("qv1_" + UUID4, result["w"])
        ):
            raise ValueError()
        return result
    except (ValueError, TypeError, KeyError):
        raise DomainError(422, "VALIDATION_ERROR", "invalid feed cursor") from None


def _render(db, meta, row, offset, limit, now):
    _check_snapshot(meta, row, now)
    ids = json.loads(row["ordered_ids"])
    if offset > len(ids):
        raise DomainError(422, "VALIDATION_ERROR", "invalid cursor ordinal")
    all_rows = folded(db, now)
    subs = {s["subscription_id"]: s for s in visible_subscriptions(db)}
    # Every captured item must remain valid, including those beyond the current page.
    if any(
        identifier not in all_rows or all_rows[identifier]["subscription_id"] not in subs
        for identifier in ids
    ):
        raise conflict()
    ratings = json.loads(row["ratings_json"])
    items = []
    for identifier in ids[offset : offset + limit]:
        tweet = all_rows[identifier]
        sub = subs[tweet["subscription_id"]]
        rating = ratings[tweet["project_id"]]
        items.append(
            {
                "activity_id": identifier,
                "subscription_id": sub["subscription_id"],
                "project_id": sub["project_id"],
                "tweet_id": tweet["tweet_id"],
                "name": sub["name"],
                "x_handle": sub["handle"],
                "notes": sub["notes"],
                "rating": rating["rating"],
                "rating_revision": rating["revision"],
                "tweet_kind": tweet["tweet_kind"],
                "text": tweet["text"][:20000],
                "quoted_tweet": quote_for(db, tweet["tweet_id"]),
                "translation_zh": translation_for(db, tweet["tweet_id"]),
                "url": f"https://x.com/{sub['handle']}/status/{tweet['tweet_id']}",
                "occurred_at": iso(int(tweet["created_at"] * 1000))
                if tweet["created_at"] is not None
                else None,
                "received_at": iso(tweet["first_received_at_ms"]),
                "sort_at": iso(tweet["sort_at_ms"]),
                "sort_basis": "occurred_at" if tweet["created_at"] is not None else "received_at",
                "media": None,
                "interactions": None,
                "important": None,
            }
        )
    return {
        "profile": PROFILE,
        "policy_version": POLICY,
        "snapshot": {
            "snapshot_id": row["snapshot_id"],
            "as_of": iso(row["as_of_ms"]),
            "expires_at": iso(row["expires_at_ms"]),
            "ratings_catalog_version": row["catalog_version"],
            "ratings_source_state": "verified" if row["catalog_version"] is not None else "not_needed",
        },
        "items": items,
        "next_cursor": _cursor(meta, row, offset + limit) if offset + limit < len(ids) else None,
        **json.loads(row["counts_json"]),
    }


def snapshot(store, request: SnapshotRequest):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = retention_now(db)
        base = db.execute("SELECT * FROM feed_bases WHERE basis_id=?", (request.basis_id,)).fetchone()
        if base is None or base["actor_hash"] != actor_hash(request.actor):
            raise DomainError(404, "NOT_FOUND", "feed basis not found")
        meta = db.execute("SELECT * FROM feed_meta WHERE singleton=1").fetchone()
        _check_snapshot(meta, base, now)
        if base["prepared_until_ms"] <= now:
            raise conflict("feed basis preparation expired")
        if base["query_hash"] != request.query_hash:
            raise DomainError(422, "VALIDATION_ERROR", "query binding mismatch")
        expected = json.loads(base["project_ids"])
        ratings = request.ratings_snapshot
        try:
            checked = parse_time(ratings.checked_at)
        except ValueError:
            raise DomainError(503, "UPSTREAM_UNAVAILABLE", "invalid ratings timestamp") from None
        from . import retention

        wall_now = retention.wall_ms()
        items = {r.project_id: r.model_dump() for r in ratings.items}
        if (
            set(items) != set(expected)
            or len(items) != len(ratings.items)
            or checked < wall_now - 15000
            or checked > wall_now + 5000
            or bool(expected) != (ratings.catalog_version is not None)
        ):
            raise DomainError(503, "UPSTREAM_UNAVAILABLE", "incomplete or stale ratings projection")
        for r in ratings.items:
            if (r.state == "missing" and (r.rating is not None or r.revision is not None)) or (
                r.state == "found" and r.revision is None
            ):
                raise DomainError(503, "UPSTREAM_UNAVAILABLE", "invalid ratings item")
        query = Query.model_construct(**json.loads(base["query_json"]))
        all_rows = folded(db, now)
        subs = {r["subscription_id"]: r for r in visible_subscriptions(db)}
        candidate_ids = json.loads(base["candidate_ids"])
        if any(aid not in all_rows for aid in candidate_ids):
            raise conflict()
        counts = {r: 0 for r in ("S", "A", "B")}
        sub_counts = counts.copy()
        excluded = {r: 0 for r in ("reply", "repost", "unknown_type", "C", "D", "unrated", "missing_project")}
        chosen = []
        for sid in json.loads(base["subscription_ids"]):
            if sid not in subs:
                raise conflict()
            r = items[subs[sid]["project_id"]]
            if not subs[sid]["removal_complete"] and r["state"] == "found" and r["rating"] in sub_counts:
                sub_counts[r["rating"]] += 1
        for aid in candidate_ids:
            tweet = all_rows[aid]
            kind = tweet["tweet_kind"]
            if kind not in ("original", "quote", "unknown"):
                excluded[kind if kind in ("reply", "repost") else "unknown_type"] += 1
                continue
            rating = items[tweet["project_id"]]
            if rating["state"] == "missing":
                excluded["missing_project"] += 1
            elif rating["rating"] in ("C", "D"):
                excluded[rating["rating"]] += 1
            elif rating["rating"] is None:
                excluded["unrated"] += 1
            else:
                counts[rating["rating"]] += 1
                if rating["rating"] in query.ratings:
                    chosen.append(aid)
        chosen.sort(key=lambda aid: (all_rows[aid]["sort_at_ms"], aid), reverse=True)
        aggregates = {
            "matched_total": len(chosen),
            "activity_counts_by_rating": counts,
            "subscription_counts_by_rating": sub_counts,
            "excluded": excluded,
            "count_scopes": {"activities": "filtered_feed", "subscriptions": "all_visible_subscriptions"},
        }
        row = {
            "snapshot_id": "fsn_" + str(uuid.uuid4()),
            "actor_hash": base["actor_hash"],
            "query_view_id": base["query_view_id"],
            "query_hash": base["query_hash"],
            "semantic_revision": base["semantic_revision"],
            "snapshot_epoch": base["snapshot_epoch"],
            "as_of_ms": base["as_of_ms"],
            "expires_at_ms": min(
                [base["expires_at_ms"]] + [all_rows[aid]["expires_at_ms"] for aid in candidate_ids]
            ),
            "catalog_version": ratings.catalog_version,
            "ordered_ids": canonical(chosen),
            "ratings_json": canonical(items),
            "counts_json": canonical(aggregates),
        }
        db.execute("DELETE FROM feed_bases WHERE basis_id=?", (request.basis_id,))
        capacity(db, sum(len(v.encode()) for v in row.values() if isinstance(v, str)))
        db.execute(
            "INSERT INTO feed_snapshots(" + ",".join(row) + ") VALUES(" + ",".join("?" for _ in row) + ")",
            tuple(row.values()),
        )
        result = _render(db, meta, row, 0, request.limit, now)
        db.execute("COMMIT")
        return result


def page(store, request: PageRequest):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = retention_now(db)
        meta = db.execute("SELECT * FROM feed_meta WHERE singleton=1").fetchone()
        value = _decode(meta, request.cursor)
        if value["a"] != actor_hash(request.actor):
            raise DomainError(404, "NOT_FOUND", "feed snapshot not found")
        if value["w"] != request.query_view_id:
            raise DomainError(422, "VALIDATION_ERROR", "cursor view binding mismatch")
        row = db.execute("SELECT * FROM feed_snapshots WHERE snapshot_id=?", (value["s"],)).fetchone()
        if row is None:
            raise conflict()
        if row["catalog_version"] != request.verified_catalog_version:
            raise conflict("ratings catalog changed")
        for key, column in [
            ("a", "actor_hash"),
            ("q", "query_hash"),
            ("r", "semantic_revision"),
            ("c", "catalog_version"),
            ("e", "expires_at_ms"),
            ("x", "snapshot_epoch"),
            ("w", "query_view_id"),
        ]:
            if value[key] != row[column]:
                raise DomainError(422, "VALIDATION_ERROR", "cursor binding mismatch")
        result = _render(db, meta, row, value["n"], request.limit, now)
        db.execute("COMMIT")
        return result
