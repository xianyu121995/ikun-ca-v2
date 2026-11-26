# X filtered stream for ikun-tracking-live

Tracking no longer calls 6551 for account watches or live posts. `services/tracking-worker` uses the X API v2 filtered stream:

- Rules: `GET` and `POST https://api.x.com/2/tweets/search/stream/rules`
- Stream: `GET https://api.x.com/2/tweets/search/stream` (one persistent HTTP connection per app)
- Rule per watched account: `from:{handle} -is:retweet -is:reply` with tag `ikun-ca-v2:tracking:{handle}`

That rule keeps original posts and quotes, and excludes retweets and replies. Adding or deleting a rule does not disconnect the stream. On startup and whenever project monitoring changes, reconcile creates a rule for each `desired=running` project that does not already have one, and deletes the rule when monitoring is removed. Existing `tracking.db` projects and tweets are not wiped.

Pay-per-use filtered stream does not provide Enterprise backfill. The worker does not send `backfill_minutes` and does not poll user timelines. Short disconnects can miss posts. Leave `IKUN_TRACKING_BACKFILL_ENABLED=0` and `IKUN_6551_BACKFILL_DAILY_LIMIT=0`.

Handles listed in `shared_watch_ids` stay read-only: tracking will not create or delete those rules. A shared handle only stays active when a filtered-stream rule with that configured id already exists.

Billing for the stream is about $0.005 per unique post per UTC day. The app allows 1000 rules and one connection; the current running set fits.

## Bearer token

The token is an app-only Bearer token (public reads) from the X developer console. Tracking reads it only at runtime:

1. Environment variable `IKUN_TRACKING_X_BEARER_TOKEN`, or
2. `token_file` in the tracking config: an absolute path to a mode `0600` file whose entire contents are the token and nothing else.

`IKUN_TRACKING_6551_TOKEN` is not read. Do not put the bearer in git, in this repository's unit files, in a world-readable `.env`, or in chat.

On the production host, `ikun-tracking-live` starts through `run_production.py tracking`, which loads `/var/lib/ikun/production/config/tracking.live.environment.json` (mode `0600`) into the process environment. Add the key there:

```json
"IKUN_TRACKING_X_BEARER_TOKEN": "<app-only bearer>"
```

Or point `token_file` in `/var/lib/ikun/production/config/tracking.live.json` at a separate mode `0600` file. Restart `ikun-tracking-live` only when you intend to pick up the token. This change does not deploy or restart the service.

The stream sends a blank keep-alive about every 20 seconds. The worker reconnects if nothing arrives for 25 seconds. A rejected bearer is recorded as tracking runtime error `stream_auth_rejected` and as the health line `实时推文流鉴权被拒绝`. That line is not a 6551 quota error. The 6551 REST ledger is unchanged and is still what hunter uses.
