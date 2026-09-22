# Venom provider concurrency investigation

The advertised account metadata (`max_connections=1`) and local Dispatcharr
account/profile cap (1) were previously described too strongly as a confirmed
provider limit. The user reported simultaneous phone and TV playback.

## Method

`ops/venom-provider-concurrency-probe.py` runs inside Dispatcharr's Django shell.
It reads existing source URLs privately, without changing gateway limits or
credentials. It checks gateway occupancy before starting and between stages.
Eight distinct live provider IDs are first decoded individually. Concurrent
stages use 2, 3, 4, 6, and 8 sources, real-time FFmpeg input pacing, 20 seconds
of video decoding per source, one decoder/filter thread per process, bounded
network/process timeouts, and eight-second recovery pauses. First unstable stage
stops the sweep; that alone is not enough to attribute failure to a quota.

The decoder checks decoded duration, frame count and successful process exit,
not merely HTTP 200. Process overlap must be at least 19 seconds. No full movie
download, permanent capacity setting change, credentials logging, or gateway
limit evasion is performed. Direct-provider testing intentionally isolates the
provider's behaviour from the local gateway's one-stream cap.

`VENOM_PROBE_MODE=mixed` tests one live source plus one movie and one episode,
after individual baselines, using 60 seconds of real-time decoding.

## Results so far

**Method correction:** the original tests below used FFmpeg `-t`, a media-time
cutoff. MPEG-TS discontinuities can affect early successful exits. They establish
that concurrent decoding occurred, but early exits alone do NOT establish that
the provider disconnected a stream. Any provisional three/four-stream boundary
is withdrawn pending the wall-clock tests. `wall_decode` omits `-t`, waits 60
wall seconds, requires a live process at the deadline, fresh progress, and frame
advancement during the last ten seconds, then deliberately stops its own decoder.
The revised modes are `wall` (2/4/6/8 live) and `wallmixed` (live+movie, then
live+movie+episode). Failures still stop upward testing.

## Corrected wall-clock results (use these for decisions)

- Two different live streams: source 96396 exited at 58.77 seconds; 157664
  remained alive and advancing at 60 seconds. The sweep stopped at two.
- Live + movie: both alive and advancing at 60 seconds, passed.
- Live + movie + episode: live exited at 45.82 seconds; both VOD streams
  remained alive and advancing at 60 seconds. Failed as a sustained trio.
- The same live source alone: alive and advancing at 90 seconds, passed.
- Two gateway viewers of the same channel: statistics confirmed **one gateway
  live channel and two clients**. Both stayed alive and advancing for 90 wall
  seconds; both passed. Existing gateway sharing is functional without raising
  provider account/profile capacity. Both decoders were deliberately stopped.

Consequently the advertised one-stream quota is not an immediate universal
block, but neither two nor three is a proven universally reliable distinct-source
capacity. No exact hard maximum was established. Do not raise the permanent
gateway account cap solely from brief simultaneous connection success.

- Initial unpaced pair: both distinct channels decoded 20 seconds of video;
  process overlap 8.43 seconds. This is preliminary evidence, not sustained proof.
- All eight live-source individual baselines succeeded.
- Real-time two-channel test: passed, 20.61 seconds process overlap.
- Real-time three-channel test: passed, 20.57 seconds process overlap.
- Real-time four-channel test: passed, 20.51 seconds process overlap.
- Six-channel stage: five decoded the full 20 seconds; provider source 80 decoded
  18.14 seconds. All exited zero, and all six received video. Strict full-duration
  gate failed, so eight was not attempted.
- Repeat individual baseline for source 80 then failed with exit 8 and no frames.
  Therefore six is **not** an established concurrency ceiling. Source 80 was
  replaced by previously-working source 157664 for longer confirmation tests.
- A fresh provider account API read still returned max_connections 1, status
  Active, active_cons 0 between stages. That metadata did not predict observed
  concurrent playback and is not a substitute for decoding measurements.
- Five streams for 60 seconds: sources 96396, 157664, 506104 completed; source
  519189 ended at 30.20 seconds and 579913 at 34.16 seconds. No HTTP rejection
  code was captured. Sweep stopped without attempting six or eight. This proves
  that this five-source set was not stable for a minute, not why it failed.
- Follow-up boundary test uses sources 96396, 157664, 506104, 157652 at three,
  then four concurrent streams for 60 seconds. Three passed: overlap 60.63 seconds,
  all three decoded 60 seconds. Four failed: sources 96396 and 157664 ended after
  27.90 and 27.32 seconds; the other two decoded 60 seconds. This is substantially
  stronger evidence of concurrency-associated instability than the initial
  six-source test, since the first three had just passed together.
- Highest fully successful sustained stage: three distinct live sources for one
  minute. Four and five are not reliable based on these tests. Exact provider
  enforcement remains unproven; no explicit quota HTTP response was captured.
- Eight was intentionally not attempted after failures at lower concurrency.
- Local gateway cap is unchanged. No bypass, identity rotation, or alternate
  credentials were used.
- Mixed three-stream test: movie 580670 and episode 23797 completed 60 seconds;
  live source 96396 ended at 43.20 seconds. Therefore three is not a proven
  reliable cross-content capacity, despite the successful three-live test.
- Two-stream live/live and live/movie follow-ups are pending. No permanent
  gateway capacity change should be based on the initial short tests alone.

These are observations from one source IP and one short test window. They do
not establish a contractual allowance, multi-IP behaviour, long-session
stability, or an exact maximum unless a repeatable failure boundary is found.
Do not use them to claim unlimited connections.
