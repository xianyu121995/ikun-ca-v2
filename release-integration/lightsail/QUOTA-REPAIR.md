# 6551 quota repair and WSS-only tracking (2026-10-22 owner approval)

WSS ingestion uses local desired-running state, subscription ownership and stable author identity.
REST availability, unknown/retrying remote status and expired Watch observations do not revoke that
authorization. Unsubscribed/stopped/removed subscriptions and identity/ownership conflicts still reject.

## REST policy

Tracking, Hunter profile/Watch and Hunter AI tweet reads share `IKUN_6551_LEDGER` (an operational SQLite
ledger, separate from domain databases). `IKUN_6551_DAILY_LIMIT=300` limits **all** 6551 REST attempts;
`IKUN_6551_BACKFILL_DAILY_LIMIT=0` disables tweet recovery by default. The recovery cap permits zero.
`IKUN_TRACKING_BACKFILL_ENABLED=0` is an independent default-off guard. The preserved recovery path
requires an explicit `1` switch AND a positive recovery cap; deployed tracking uses neither.
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

Tracking is passive WSS only: no disconnect-gap recovery, restart recovery or new-account initial
REST read. The worker does not create/consume recovery jobs or record new recovery gaps while disabled.
Existing operational recovery jobs remain inert. Both the tracking transport and shared accounting
gate reject tracking data-read endpoints before network I/O, even if called directly. A zero cap also
blocks recovery when the optional switch is accidentally enabled. Watch listing/creation/removal are
control-plane REST operations and remain event-triggered as explicitly requested; they are not tweet
backfill. New subscriptions start with WSS events after Watch setup, with existing author, ownership,
generation and deduplication checks retained. Disconnect periods are intentionally not backfilled.

The optional recovery implementation is retained for regression coverage. If explicitly enabled in a
future operator-approved change, it still has single-attempt durable jobs, exact local gap filtering,
100-result bounds and no automatic pagination or paid replay. This document does not authorize enabling it.

## Visibility and deployment

The authenticated health endpoint publishes allowlisted aggregate counts from `ops/6551-status.json`.
The banner shows today's usage by program and the configured caps. Historical requests before this
release are explicitly excluded. The manual check only queues a check and obeys the quota circuit.

Deploy with `deploy_quota_fix.py --prepare-only` to copy the exact active immutable release, overlay
only the reviewed Git files and build the website without touching active services. `--final --prepared`
verifies the archive/source/build marker, obtains verified online SQLite backups and private config
backups, then restarts only tracking, Hunter and web. Projects/tunnel PIDs must remain unchanged.
The known empty quota is seeded as an open circuit, so startup does not immediately probe or backfill.
`--tracking-wss-only` installs the zero budget and disabled switch in all three environments so shared
status publication stays consistent. `--gap-backup` cannot seed recovery in that mode.
No deployment step calls a supplier endpoint or changes a Watch. Do not run legacy retry scripts.

## Expected request volume

Tracking tweet-data REST calls are zero, including new accounts and reconnects. Add only one shared
Watch snapshot per requested control-plane trigger and legitimate account lifecycle writes. Hunter
discovery/profile/AI reads add their actual demand and were not disabled by the tracking decision.
All permitted 6551 REST calls still share the 300/day hard ceiling. Zero recovery budget must not be
misreported as an exhausted global REST budget; the website displays recovery as disabled.
At zero quota, normal REST attempts stop; only sparse due Watch probes are allowed. WSS handshakes
are accounted separately from REST and are not described as billable REST requests.

Offline tests prove policy behavior; real new-tweet delivery cannot be claimed while both upstream
WSS handshakes are rejected with HTTP 401. It requires an actual subscription ACK/pong and a new
accepted tweet after quota/access restoration. 401 itself does not prove whether quota or credentials
caused the upstream rejection; the quota diagnosis also uses the owner's provider-console evidence.

## Read-only Hunter split investigation

Tokyo code (`Store.apply_profile`) selects WSS at >=5000 followers, REST below 5000. REST accounts use
`GET https://api.twitterapi.io/twitter/user/followings` with pageSize=20 and cursor="" every 3600 seconds
after success; the first successful response establishes a baseline. Subsequent differences enter the
same event pipeline. This is a local frozen routing policy; the public 6551 Watch documentation lists
`newFlwBol` but does not document a 5000-follower eligibility guarantee. No provider request or Watch
change was made to test low-follower eligibility. Do not equate tweet WSS support with following-event
support, and do not claim that switching a local mode makes the upstream send those events.

Read-only Tokyo inventory during this change: 69 enabled REST accounts, 19 enabled WSS accounts,
2 disabled WSS accounts; configured TwitterAPI budget 100000 credits/day. Full hourly polling of 69
accounts at 20 returned followings per call costs approximately 69*24*60=99360 credits, or $0.9936/day
at the published $1=100000 credits rate (excludes retries and reflects full operation, not measured billing).
One REST account has a persisted ambiguous-billing error and is not blindly retried. The latest stored
Watch inventory is 234/600, a historical snapshot, not a fresh entitlement check. Moving all enabled
REST accounts could require up to 69 new Watch rows or safely authorized flag changes to existing rows.

All-WSS could remove those hourly TwitterAPI Following reads and reduce their polling delay/20-result
window, but requires confirmed low-follower Following-event support, Watch ownership/capacity and actual
6551 charging terms. It increases dependence on 6551 availability; current WSS 401 means no proven
working replacement. WSS does not provide guaranteed gap replay. Hunter routing, thresholds, existing
Watches, profiles and business data were left unchanged.

Public primary references checked 2026-10-22:
- https://raw.githubusercontent.com/6551Team/opentwitter-mcp/main/openclaw-skill/opentwitter/SKILL.md
- https://docs.twitterapi.io/api-reference/endpoint/get_user_followings
- https://twitterapi.io/pricing
