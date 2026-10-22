# Hunter REST-only hourly batches

Spec: phase2-v1.0.0. Candidate base: `7fa16d69fdbc8c7151c46b0dbbcc29b92cc106fb`.
User scope: move all Hunter discovery to TWI, preserve Tracking, scan each Hunter
hourly in twelve staggered cohorts. No production action is performed by tests.

## Runtime configuration for the approved release

Set only the Hunter environment:

```json
{
  "HUNTER_REST_ONLY": "1",
  "HUNTER_TWITTERAPI_DAILY_CREDITS": "150000",
  "HUNTER_REST_CONCURRENCY": "2"
}
```

Keep existing formal-mode, external-I/O and direction credentials. No secrets are
included here. The default remains legacy-compatible until the flag is enabled.

## Scheduling and migration

- UTC wall-clock five-minute slots, twelve per hour; local Beijing times are
  likewise `:00, :05, ..., :55`. Initial 85 accounts form eleven cohorts of 7 and
  a final cohort of 8, ordered by existing creation time and ID.
- The sole Hunter worker stores cohort membership, last dispatched slot and
  per-account attempts in `state/rest_batches:v1`. Only the current cohort is
  dispatched; missed slots are skipped rather than replayed together. Within a
  cohort existing bounded concurrency and the shared rate limiter still apply.
  Members becoming due later inside the same five-minute slot can still dispatch
  once; a slot's earlier dispatched members cannot repeat.
- Successful polls keep the next fixed cohort time, independent of request
  completion delay. Existing future `next_poll_at` values/backoff are honored;
  during first alignment some accounts can wait for their following cohort.
- A crash after dispatch claim but before receiving a durable result can skip
  that account for one cycle. Unknown billed attempts remain fenced for explicit
  reconciliation; no automatic replay or clearing of `billing_unknown`.
- Add/remove/disable minimally rebalances membership. Rebalancing can extend one
  interval; it cannot trigger a burst or repeat an account inside twelve slots.
- Existing WSS Hunters stay marked WSS until their first valid TWI response.
  That response atomically switches to a new generation and seeds a baseline,
  with **zero historical-follow alerts**. IDs, historical signals and outbox stay
  intact. `state/rest_cutover:<id>` records the committed baseline and pending
  external Watch cleanup. Failed accounts stay pending individually.
- WSS source and Watch management are disabled for Hunter as soon as REST-only
  starts. The transition therefore has a per-account observation gap until its
  first baseline, at most one normal batch cycle if the provider succeeds.
- Profile resolution uses TWI regardless of follower count. AI profile/tweet
  enrichment also uses TWI and the same daily budget; no Hunter 6551 call remains
  in this runtime policy. Tracking code, configuration and Watch stay unchanged.
- Successful paid profile/following results persist before clearing the payment
  intent. Baseline/profile commits consume results atomically. Enrichment results
  are cached for an hour. Startup following replay performs local writes only.
- Restore rejects snapshots whose REST checkpoints, paid results or Hunter
  baselines disagree with the stopped latest source. Use a coherent fresh backup;
  never combine an old WSS baseline with a new scheduler or cutover marker.

## Offline validation

From `services/hunter-worker/python`, using the existing Python 3.11 test runtime:

```sh
PYTHONPATH=.:../../../packages/runtime/python /absolute/path/to/python3.11 -m pytest -q
```

Tests use temporary Hunter stores and `httpx.MockTransport`. Coverage includes
85 accounts across three hours, restarts, slow responses, skipped slots, clock
rollback, membership edits, independent failures, preserved payment fences,
WSS baseline/history preservation, transaction rollback, paid response recovery,
TWI-only profiles/AI, 402 provider-wide blocking and coherent/failing restores.
No provider requests, real Watch writes, deployment or Tracking mutation.
The pre-existing exact-72h test used wall-clock milliseconds plus a microsecond
float addition and intermittently lost the extra microsecond (also reproduced
on the unchanged production source). Its test reference now uses whole seconds;
the production retention/window calculation is unchanged.

## Deployment acceptance and later cleanup

Deployment approval must bind the final candidate SHA. Before cutover, verify
the current release and exact enabled Hunter set, then take a self-contained
SQLite backup and save Hunter configuration. Restart only Hunter with the new
policy. Verify its sole worker lease, persisted cohorts, 19 baseline commits,
unchanged existing TWI payment fences and unchanged Tracking process/state.
Observe actual cohort execution before claiming live acceptance.

Only after all corresponding REST baselines are verified may the approved 19
Hunter Watch rows be removed. Do not remove a failed/pending account's Watch or
any Tracking row. Retain the pre/post exact Watch inventories.

Group audit from the pre-migration inventory: `小龙虾` still contains four Tracking
accounts after Hunter migration; `ikun-ca-v2-project-tracking` and `ikun-website`
also contain Tracking. Keep these. `ikun-ca-v2-hunters` becomes a cleanup candidate
only after its sole Hunter is migrated. `airdrop-hunters`, `X监控`, `猎手监控`,
`待做项目监控` were empty; recheck references, membership and delete semantics
before deleting any group. Do not test deletion on a nonempty group.

After rollout, monitoring should expect Hunter REST plus Tracking WSS. Do not
continue treating Hunter's intentionally disabled WSS as a connection failure.

TWI followings remains the existing single newest-first page of 20; more than
20 follows in an interval can be missed. The hourly followings floor is
85 × 24 × 60 = 122,400 credits/day, before AI/profiles and failures. Reservations
are conservative (profile 18, latest-tweet page up to 20 × 15 = 300). Reaching the
150,000 cap pauses new paid calls until the budget window permits them.

Official contracts reviewed:
- https://docs.twitterapi.io/api-reference/endpoint/get_user_followings
- https://docs.twitterapi.io/api-reference/endpoint/get_user_by_username
- https://docs.twitterapi.io/api-reference/endpoint/get_user_last_tweets
- https://twitterapi.io/pricing
