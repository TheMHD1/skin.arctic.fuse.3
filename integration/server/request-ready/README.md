# Request-ready notifier and Seerr webhook repair

The request-ready worker uses Python's standard library and polls Seerr; it
does not need or take over Seerr's single existing webhook slot. The existing
webhook serves CT103's Arabic-fulfillment integration.

Deployment status (September 23): installed as the provided oneshot systemd
service and a 60-second timer with a small randomized delay. Historical seeding
and subsequent polls completed successfully. The service is normally inactive
between timer runs; this is not a failed daemon. Twelve unit tests cover
readiness, delivery, 4K request-season semantics and webhook persistence.
A real newly-completed request has not yet been observed delivering a message.

The separate `repair-seerr-webhook.py` is a one-time, narrow Seerr 3.4.1
maintenance tool. It does not alter the request-ready worker or install another
webhook. Seerr's installed webhook agent double-parses its base64 payload;
the supported settings API expects a JSON **string** in `options.jsonPayload`
and stores its JSON-string encoding. An older stored base64 JSON object caused
`"[object Object]" is not valid JSON` before delivery. The tool checks the
installed parser source and version, compares API and on-disk settings,
creates an exclusive mode-0600 backup, POSTs the full existing agent with only
the payload encoding normalized, then checks API and persisted readback.
It is idempotent. Run inside the Seerr host/container namespace with its private
settings file and Docker access; never commit the backup or credentials.

On 2026-09-22 it repaired the live CT102 webhook via Seerr's supported API.
The existing URL, headers, enabled state and event mask were preserved. Its
receiver is CT103's `arabic-fulfillment` `/jellyseerr-hook`, not Moonbase. The
receiver source explicitly ignores test payloads without a TMDb ID; the Seerr
test endpoint returned 204 after repair. Previously failed events were not
replayed. Keep the existing webhook configured; request-ready polling does not
depend on it.

## What qualifies as ready

The worker reads Seerr `GET /api/v1/request` in complete bounded pages. On its
first successful snapshot, it records every existing request and suppresses
notification for those already available. Requests that were pending at first
boot and requests created afterward can become events. One SQLite event is
stored per Seerr request ID, including separate requests for the same title.

An approved/completed movie request needs Seerr media status `AVAILABLE` and
a requester-visible Jellyfin `Movie` with a media source in an owned library.
A TV request needs **every requested season** marked available in Seerr and
at least one requester-visible playable episode in each requested season.
Seerr's whole-show partial status alone is insufficient. The 4K request flag
selects Seerr's 4K status and Jellyfin media ID. The worker checks the
requester's Jellyfin ID, obtains that user's views, and searches only those
owned movie/show or mixed library parents for the exact item ID. Venom views,
music, Live TV, collections and playlist views cannot satisfy readiness.
Missing mappings, sources or access leave the request eligible for later polls.

Each poll reads at most 20 Seerr pages of 100 requests. It verifies at most 20
eligible requests per cycle, rotating a saved cursor so one unavailable item
does not starve others. For a TV season, it inspects at most 50 returned
episodes and stops at the first playable one. These limits can delay a true
positive in very large or unusual libraries; they never cause a false ready
event. An incomplete Seerr snapshot is rejected without seeding or changing
request state. Network calls time out after eight seconds.

## Delivery and its limit

Events remain in the SQLite outbox until Jellyfin accepts a
`POST /Sessions/{sessionId}/Message` command with HTTP 204. The worker selects
only an active session whose `UserId` exactly equals the Seerr requester's
Jellyfin ID and whose supported commands include `DisplayMessage`. If that
user is playing or paused in any active session, delivery waits. No matching
idle session also leaves the event pending. Errors retry with a bounded
exponential delay. The event row is retained after acceptance so a later Kodi
or Web consumer can use the same outbox. No HTTP listener is exposed.

Jellyfin 204 confirms that a command was accepted, **not** that a person saw
it. Some native clients do not advertise or display session messages, and
there is no offline OS notification. To alert a phone while the app is closed,
enable Seerr's built-in per-user email or web push separately. Seerr's web
push requires HTTPS and user opt-in; mobile web push also requires the Seerr
PWA. Seerr's own alert follows Seerr's availability state and can arrive
before this worker verifies playable media. Moonbase may offer Moonfin mobile
push, but its webhook must not be overwritten and its availability event alone
does not perform this worker's playability check.

## Private configuration and runbook

Create a root-owned or dedicated-service-user-readable JSON file outside Git:

```json
{
  "seerr_url": "http://seerr-internal:5055",
  "seerr_key_file": "/private/request-ready/seerr-api-key",
  "jellyfin_url": "http://jellyfin-internal:8096",
  "jellyfin_key_file": "/private/request-ready/jellyfin-api-key",
  "state_db": "/private/request-ready/state.sqlite3",
  "poll_seconds": 300
}
```

Use a Jellyfin key with permission to read user-scoped views/items and
sessions and to send session messages. The worker sends it with Jellyfin 12's
`Authorization: MediaBrowser Token="…"` header. Keep that privilege and both keys in
private deployment storage; restrict DB access because it contains requester
IDs and requested titles. Do not commit config, tokens, raw requests, logs,
media inventories or the SQLite database. The provided file paths are
illustrative and are not installed by this repository.

First, run `python3 worker.py --config /private/request-ready/config.json
--once` on a saved private state path. Check only the returned event counts,
then inspect the database privately before scheduling it. The first complete
poll seeds historical available requests without alerting. Do not delete the
state DB after production use: doing so would suppress all requests already
available at the next first boot. A systemd timer or long-running service can
invoke the same command; without `--once` it polls every `poll_seconds` (at
least 30 seconds). Stop the process to pause delivery; existing events remain
recoverable in SQLite. Back up the DB privately before a source update.

Verification before deployment:

```sh
python3 -m unittest discover -s integration/server/request-ready -p 'test_*.py' -v
python3 -m py_compile integration/server/request-ready/worker.py
```

Read-only source references: [Seerr requests](https://docs.seerr.dev/api/get-all-requests/),
[Seerr media scans](https://docs.seerr.dev/using-seerr/settings/mediaserver/),
[Jellyfin session message API](https://typescript-sdk.jellyfin.org/interfaces/generated-client.SessionApiSendMessageCommandRequest.html),
[Seerr web push](https://docs.seerr.dev/using-seerr/notifications/webpush/).
