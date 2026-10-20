"""Restore only unknown tweet types from saved evidence; dry-run unless --apply.

Run with the tracking venv and release PYTHONPATH. No remote API or Watch calls.
The CLI requires a verified four-store backup and a stopped tracking worker for writes.
"""
import argparse
import json
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

KNOWN = {"original", "quote", "reply", "repost"}


def restore(db, since, *, apply=False):
    from tracking.commands import activity, change
    from tracking.feed import activity_id
    from tracking.protocol import SCOPE, canonical

    candidates = [dict(r) for r in db.execute(
        "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id) "
        "WHERE t.received_at>=? AND t.tweet_kind='unknown' AND t.author_verified=1 "
        "AND t.expires_at_ms>? AND t.handle!='tampad_' ORDER BY t.seq",
        (since, time.time()*1000),
    )]
    wanted = {(r["subscription_id"], r["tweet_id"]) for r in candidates}
    evidence = {}
    for row in db.execute("SELECT seq,data FROM changes WHERE event_type LIKE 'tracking.feed.activity.%' ORDER BY seq"):
        value = json.loads(row["data"])
        key = (value.get("subscription_id"), value.get("tweet_id"))
        if key in wanted and value.get("source") == "wss" and value.get("tweet_kind") in KNOWN:
            evidence[key] = (value["tweet_kind"], "saved_wss_event:"+str(row["seq"]))
    plan, unresolved = [], []
    for row in candidates:
        found = evidence.get((row["subscription_id"], row["tweet_id"]))
        if not found:
            receipt = db.execute("SELECT result FROM receipts WHERE key=?", ("tracking.quote.v1:"+row["tweet_id"],)).fetchone()
            if receipt:
                from tracking.events import quoted_context
                q = json.loads(receipt[0])
                if isinstance(q, dict) and quoted_context({"quotedStatus": {
                    "id":q.get("tweet_id"), "text":q.get("text"), "userScreenName":q.get("author_handle")}}):
                    found = ("quote", "saved_quote_receipt")
        if not found:
            unresolved.append({"handle":row["handle"], "tweet_id":row["tweet_id"]})
            continue
        kind, source = found
        item = {"handle":row["handle"], "tweet_id":row["tweet_id"], "kind":kind, "evidence":source}
        plan.append(item)
        if not apply:
            continue
        db.execute("UPDATE tweets SET tweet_kind=?,type_evidence_version='saved-trusted-type-v2' WHERE seq=? AND tweet_kind='unknown'", (kind,row["seq"]))
        if kind in ("original", "quote"):
            db.execute("UPDATE tweet_ledger SET state='visible' WHERE tweet_id=? AND state!='expired'", (row["tweet_id"],))
        row["tweet_kind"] = kind
        value = activity(row) | {"activity_id":activity_id(row["subscription_id"],row["tweet_id"]),
                                  "tweet_kind":kind, "replay":True, "is_live_new":False}
        event_type = "tracking.feed.activity.updated.v1"
        event_id = change(db,event_type,value)
        envelope = {"schema_version":1, "event_id":event_id, "source":"tracking", "event_type":event_type,
                    "occurred_at":value["occurred_at"], "received_at":value["received_at"], "tenant_id":SCOPE,
                    "project_id":row["project_id"], "correlation_id":value["activity_id"], "payload":value}
        db.execute("INSERT INTO tracking_outbox(event_id,envelope,state,updated_at) VALUES(?,?,'pending',?)",
                   (event_id,canonical(envelope),time.time()))
        db.execute("INSERT INTO audit(project_id,actor,action,at,detail) VALUES(?,'tracking-operator','restore_tweet_type',?,?)",
                   (row["project_id"],time.time(),canonical(item)))
    if apply:
        # Invalidate pre-change published snapshots, including when all candidates remain unknown.
        db.execute("UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1")
    return {"restored":plan, "still_unknown_visible":unresolved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,required=True)
    parser.add_argument("--since",required=True,help="Timezone-aware ISO timestamp")
    parser.add_argument("--backup",type=Path)
    parser.add_argument("--apply",action="store_true")
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        parser.error("--since requires a timezone")
    path = args.db.resolve(strict=True)
    if args.apply:
        if not args.backup or subprocess.run(["systemctl","is-active","--quiet","ikun-tracking-live"]).returncode == 0:
            parser.error("verified backup and stopped tracking worker required")
        manifest = args.backup/"verification.json"
        report = json.loads(manifest.read_text())
        assert time.time()-manifest.stat().st_mtime<1800, "fresh_backup_required"
        assert set(report["databases"]) == {"auth","projects","hunter","tracking"}
        assert all(v["bytes"]>4096 and v["integrity"]=="ok" and v["all_table_counts_match"] for v in report["databases"].values())
        assert (args.backup/"tracking.db").stat().st_size == report["databases"]["tracking"]["bytes"]
    with sqlite3.connect(path.as_uri()+('?mode=rw' if args.apply else '?mode=ro'),uri=True,timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE" if args.apply else "BEGIN")
        if args.apply:
            for table, count in report["databases"]["tracking"]["counts"].items():
                assert db.execute('SELECT count(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]==count, "backup_source_count_changed:"+table
        result = restore(db,since.timestamp(),apply=args.apply)
        if args.apply:
            assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            db.commit()
        else:
            db.rollback()
    print(json.dumps({"applied":args.apply,**result},ensure_ascii=False))


if __name__ == "__main__":
    main()
