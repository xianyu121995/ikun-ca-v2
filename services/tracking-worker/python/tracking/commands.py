"""Atomic command inbox and projections over the existing tracking store."""

import hashlib
import time
import uuid

from .protocol import DomainError, canonical, utc


def result(row, request_id):
    return {
        k: row[k] for k in ("command_id", "state", "project_id", "subscription_id", "revision", "error_code")
    } | {"updated_at": utc(row["updated_at"]), "request_id": request_id}


def query(store, command_id, request_id):
    with store.connect() as db:
        row = db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
        if row is None:
            raise DomainError(404, "NOT_FOUND", "command not found")
        return result(row, request_id)


def change(db, event_type, data):
    event_id = "evt_" + str(uuid.uuid4())
    db.execute(
        "INSERT INTO changes(event_id,event_type,data,received_at) VALUES(?,?,?,?)",
        (event_id, event_type, canonical(data), time.time()),
    )
    return event_id


def accept(store, command, request_id):
    value = command.model_dump()
    semantic = {k: v for k, v in value.items() if k != "issued_at"}
    hashed = hashlib.sha256(canonical(semantic).encode()).hexdigest()
    now = time.time()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            previous = db.execute(
                "SELECT * FROM commands WHERE command_id=?", (command.command_id,)
            ).fetchone()
            if previous:
                if previous["body_hash"] != hashed:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "command ID content conflict")
                db.execute("COMMIT")
                return result(previous, request_id)
            row = db.execute("SELECT * FROM projects WHERE project_id=?", (command.project_id,)).fetchone()
            fresh = False
            if command.operation == "tracking.create":
                payload = command.payload
                if row:
                    if row["handle"] != payload["x_handle"] or (
                        row["x_user_id"] and payload["x_user_id"] and row["x_user_id"] != payload["x_user_id"]
                    ):
                        raise DomainError(409, "CONFLICT", "project X identity conflict")
                    if not row["x_user_id"] and payload["x_user_id"]:
                        if db.execute(
                            "SELECT 1 FROM projects WHERE x_user_id=? AND project_id!=?",
                            (payload["x_user_id"], command.project_id),
                        ).fetchone():
                            raise DomainError(
                                409, "CONFLICT", "X identity already belongs to a different project"
                            )
                        db.execute(
                            "UPDATE projects SET x_user_id=? WHERE project_id=?",
                            (payload["x_user_id"], command.project_id),
                        )
                else:
                    if db.execute(
                        "SELECT 1 FROM projects WHERE handle=? OR (x_user_id IS NOT NULL AND x_user_id=?)",
                        (payload["x_handle"], payload["x_user_id"]),
                    ).fetchone():
                        raise DomainError(
                            409, "CONFLICT", "X identity already belongs to a different project"
                        )
                    subscription_id = "sub_" + str(uuid.uuid4())
                    db.execute(
                        """INSERT INTO projects(project_id,subscription_id,x_user_id,name,handle,notes,confirmed_by,
                        confirmed_at,desired,generation_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,'running',?,?,?)""",
                        (
                            command.project_id,
                            subscription_id,
                            payload["x_user_id"],
                            payload["name"],
                            payload["x_handle"],
                            payload["notes"],
                            command.actor.user_id,
                            now,
                            now,
                            now,
                            now,
                        ),
                    )
                    row = db.execute(
                        "SELECT * FROM projects WHERE project_id=?", (command.project_id,)
                    ).fetchone()
                    fresh = True
            else:
                if row is None or row["subscription_id"] != command.subscription_id:
                    raise DomainError(404, "NOT_FOUND", "subscription not found")
                if row["revision"] != command.expected_revision:
                    raise DomainError(409, "VERSION_CONFLICT", "revision changed")
            desired = {
                "tracking.create": "running",
                "tracking.start": "running",
                "tracking.resume": "running",
                "tracking.stop": "stopped",
                "tracking.remove": "removed",
            }[command.operation]
            generation = not fresh and desired == "running" and row["desired"] != "running"
            db.execute(
                """UPDATE commands SET state=CASE WHEN remote_attempted=0 THEN 'failed' ELSE 'unknown' END,
                       error_code='SUPERSEDED',updated_at=? WHERE project_id=? AND state NOT IN ('succeeded','failed')""",
                (now, command.project_id),
            )
            revision = row["revision"] + (0 if fresh else 1)
            db.execute(
                """UPDATE projects SET desired=?,status='pending',error=NULL,attempts=0,next_retry=0,
                revision=?,updated_at=?,active_command_id=?,generation=generation+?,
                generation_at=CASE WHEN ? THEN ? ELSE generation_at END,
                baseline_ready=CASE WHEN ? THEN 0 ELSE baseline_ready END,
                last_backfill=CASE WHEN ? THEN NULL ELSE last_backfill END WHERE project_id=?""",
                (
                    desired,
                    revision,
                    now,
                    command.command_id,
                    int(generation),
                    generation,
                    now,
                    generation,
                    generation,
                    command.project_id,
                ),
            )
            db.execute(
                """INSERT INTO commands(command_id,body_hash,envelope,project_id,subscription_id,revision,
                state,created_at,updated_at,request_id) VALUES(?,?,?,?,?,?,'accepted',?,?,?)""",
                (
                    command.command_id,
                    hashed,
                    canonical(value),
                    command.project_id,
                    row["subscription_id"],
                    revision,
                    now,
                    now,
                    request_id,
                ),
            )
            db.execute(
                "INSERT INTO audit(project_id,actor,action,at,detail) VALUES(?,?,?,?,?)",
                (
                    command.project_id,
                    command.actor.user_id,
                    command.operation,
                    now,
                    canonical({"command_id": command.command_id}),
                ),
            )
            change(
                db,
                "command.updated",
                result(
                    db.execute("SELECT * FROM commands WHERE command_id=?", (command.command_id,)).fetchone(),
                    request_id,
                ),
            )
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
    return query(store, command.command_id, request_id)


def executing(store, row):
    with store.connect() as db:
        if not row.get("active_command_id"):
            return (
                db.execute(
                    "SELECT 1 FROM projects WHERE project_id=? AND revision=?",
                    (row["project_id"], row["revision"]),
                ).fetchone()
                is not None
            )
        # Revision and active ID fence stale tasks after a concurrent command.
        changed = db.execute(
            """UPDATE commands SET state='running',remote_attempted=1,updated_at=?
            WHERE command_id=? AND command_id=(SELECT active_command_id FROM projects WHERE project_id=? AND revision=?)
            AND state NOT IN ('succeeded','failed')""",
            (time.time(), row.get("active_command_id"), row["project_id"], row["revision"]),
        )
        return changed.rowcount == 1


def observed(db, row, changes):
    command_id = row.get("active_command_id")
    if not command_id:
        return
    cmd = db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
    if not cmd:
        return
    status = changes.get("status")
    if status in ("running", "stopped", "removed") and changes.get("remote_state") in ("active", "absent"):
        state, error = "succeeded", None
    elif "error" in changes:
        error = changes["error"]
        state = (
            "unknown" if cmd["remote_attempted"] or changes.get("remote_state") == "unknown" else "pending"
        )
    else:
        return
    db.execute(
        "UPDATE commands SET state=?,error_code=?,updated_at=? WHERE command_id=?",
        (state, error, time.time(), command_id),
    )
    if cmd["state"] != state or cmd["error_code"] != error:
        change(
            db,
            "command.updated",
            result(
                db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone(),
                cmd["request_id"],
            ),
        )
    if state == "succeeded":
        db.execute(
            "UPDATE commands SET state='failed',error_code='SUPERSEDED',updated_at=? WHERE project_id=? AND command_id!=? AND error_code='SUPERSEDED' AND state='unknown'",
            (time.time(), row["project_id"], command_id),
        )


def activity(row):
    return {
        "activity_id": row["activity_id"],
        "subscription_id": row["subscription_id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "tweet_id": row["tweet_id"],
        "x_handle": row["handle"],
        "text": row["text"],
        "url": f"https://x.com/{row['handle']}/status/{row['tweet_id']}",
        "occurred_at": utc(row["created_at"]),
        "received_at": utc(row["received_at"]),
        "source": "rest" if row["source"] == "rest_recovery" else row["source"],
        "generation": row["generation"],
    }
