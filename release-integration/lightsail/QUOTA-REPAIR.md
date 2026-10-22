# 6551 quota repair (2026-10-22 owner approval)

WSS ingestion uses local desired-running state, subscription ownership and stable author identity.
REST availability, unknown/retrying remote status and expired Watch observations do not revoke that
authorization. Unsubscribed/stopped/removed subscriptions and identity/ownership conflicts still reject.

## REST policy

Tracking, Hunter profile/Watch and Hunter AI tweet reads share `IKUN_6551_LEDGER` (an operational SQLite
ledger, separate from domain databases). `IKUN_6551_DAILY_LIMIT=300` limits **all** 6551 REST attempts;
`IKUN_6551_BACKFILL_DAILY_LIMIT=300` separately caps recovery. Both are configurable positive integers.
Days use Asia/Shanghai. Failed/ambiguous attempts count; requests are reserved before transport.
An ambiguous or failed backfill is never automatically replayed. No request body, credentials or tweet
text is recorded. Metadata records time, program, endpoint, HTTP status and a sanitized error class.

There is no healthy periodic Watch polling. Startup, WSS subscription/reconnection, account lifecycle
changes and the superadmin's CSRF-protected `检查` button request one shared full snapshot. Two workers'
near-simultaneous triggers reuse the same snapshot. A failed triggered check retries with backoff of
at least 60 seconds. Watch ownership and existing lifecycle mutation rules remain unchanged.

402 opens a cross-process REST circuit. Only one Watch read may probe at the due time: initially one
hour, then two, four and at most six hours apart. Backfill/profile/AI reads cannot act as probes.
Daily limits still apply. A successful WSS subscription does **not** clear the REST circuit.
WSS 401 reconnects wait 60, 120, 240, 480, then at least 600 seconds between attempts. No new client
connection is created by a health page or check button. The normal two service connections recover
automatically. Quota depletion plus rejected tracking WSS displays `6551 额度不足，实时推文已暂停`.

Tracking backfill has no per-account periodic timer. A new generation gets one initial latest read;
a persisted disconnect/restart gap gets at most one read per account/generation. Gap queries use
`twitter_search` with fromUser and UTC date bounds, then filter exact gap seconds locally. The API's
100-result bound is retained, with `possible_gap` rather than an unsupported completeness claim.
There is no automatic pagination or paid retry. Pending work blocked before transport survives restart.
Completed/failed/ambiguous attempts do not run twice. Graceful shutdown persists the last stream gap.

## Visibility and deployment

The authenticated health endpoint publishes allowlisted aggregate counts from `ops/6551-status.json`.
The banner shows today's usage by program and the configured caps. Historical requests before this
release are explicitly excluded. The manual check only queues a check and obeys the quota circuit.

Deploy with `deploy_quota_fix.py --prepare-only` to copy the exact active immutable release, overlay
only the reviewed Git files and build the website without touching active services. `--final --prepared`
verifies the archive/source/build marker, obtains verified online SQLite backups and private config
backups, then restarts only tracking, Hunter and web. Projects/tunnel PIDs must remain unchanged.
The known empty quota is seeded as an open circuit, so startup does not immediately probe or backfill.
`--gap-backup` may seed the initial outage from an existing verified pre-restart tracking snapshot.
No deployment step calls a supplier endpoint or changes a Watch. Do not run legacy retry scripts.

## Expected request volume

Healthy idle tracking uses zero periodic REST requests. Add one shared Watch snapshot per trigger,
one initial read per new account, and one gap read per eligible account on an actual reconnect.
Hunter discovery/profile/AI reads add their actual demand (one request per relevant input).
For roughly 60 new AI inputs/day and a few account/check events, expect roughly 60–100 requests/day;
one reconnect affecting 123 accounts adds up to 123 gap reads. All share the 300/day hard ceiling.
At zero quota, normal REST attempts stop; only sparse due Watch probes are allowed. WSS handshakes
are accounted separately from REST and are not described as billable REST requests.

Offline tests prove policy behavior; real new-tweet delivery cannot be claimed while both upstream
WSS handshakes are rejected with HTTP 401. It requires an actual subscription ACK/pong and a new
accepted tweet after quota/access restoration. 401 itself does not prove whether quota or credentials
caused the upstream rejection; the quota diagnosis also uses the owner's provider-console evidence.
