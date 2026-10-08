# Server, Web and Proxmox performance — October 8

This round measures the existing deployment and applies native configuration
where practical. It adds no native APK, GPU transcoder, permanent monitor or
Jellyfin server-core fork. Server/core changes from earlier releases remain a
separate version-pinned patch stack. Private credentials, SQL dumps, browser
states, profiles, screenshots, raw logs and rollback journals stay outside Git.

## Measured bottlenecks and applied repairs

| Layer | Finding | Applied change / evidence |
| --- | --- | --- |
| Proxmox memory | 93 GiB host, approximately 6.6 GiB available, active swapping; AI VM has 36 GiB locked huge pages, alongside a 24 GiB maximum/8 GiB minimum ZFS ARC policy | Trialled then persisted 8 GiB maximum/2 GiB minimum ARC, preserving every other ZFS knob. Later samples had approximately 12–13 GiB available and substantially less swap-out. No host reboot or VM/LXC RAM change. |
| Jellystat statistics DB | Two native orphan-cleanup calls active for more than 36 minutes; one waiting on the other. A 4 MB `work_mem` caused a repeated materialized episode subquery over approximately 410,000 rows | Native role-in-database policy: `work_mem=32MB`, `statement_timeout=5min`, `lock_timeout=15s`. Cancelled only old calls of that exact procedure, restarted only the statistics app, verified a fresh native cleanup in 0.927 seconds and no old call remaining. No SQL/schema/procedure rewrite. |
| Jellyfin Enhanced Web badges | Full user tag-cache response approximately 117.6 MB, uncompressed, taking 7.1–8.5 seconds; parse/GC long tasks over 600 ms | Native `TagCacheServerMode=false`, preserving all other settings. Existing visible-card batch pipeline fetched approximately 24.8 KB instead; no whole tag-cache fetch. Home rows and corner-rating badges remained present. |
| Web search | Existing five-second placement watcher expired before slow owned results arrived, leaving Discover above the actual library | Version-pinned Enhanced patch extends the bounded watcher to 30 seconds, coalesces DOM scans to one animation frame, and cancels pending work on replacement/detach/deadline. Only plugin-owned Discover is moved; React-owned rows are not reparented. |
| Kodi/Venom | Optional shared-favourite read used the category-loading worker | [Paired performance release](../../release/performance/README.md): one bounded optional lane, smaller favourite-key DTOs and a library-only Views lookup. |

These are bounded observations under changing import/scan workload, not a
controlled claim that every route became a fixed percentage faster. Stored swap
remaining allocated does not imply ongoing thrashing; compare actual `si/so`,
memory/I/O PSI, available memory and foreground latency. Do not run `swapoff`,
drop caches, stop legitimate downloads or reboot the host to make a graph look
clean. The AI VM's tiny ordinary RSS excludes its huge-page allocation.

Jellyfin's 16 GiB container ceiling already exceeds its measured 1–2 GiB
working set, so adding LXC RAM was not justified. Scan fan-out/metadata
concurrency were already two; no blind concurrency increase, SQLite index,
locking or database-cache change was made. Active imports, repair workers and
the native scan were distinguished from the stuck statistics job.

The badge change removes unnecessary transfer and parse work; it does not make
all metadata queries instant. One early small batch still took about ten
seconds under server load. Missing upstream artwork, cold metadata, storage
I/O and provider stream buffering can remain independent limits. IMDb/native
community-score semantics, request permissions and existing Home rows remain
unchanged. No rating, HDR quality or stream capability is invented.

## Proxmox rebuild and rollback

`arc_budget.py` requires the exact full module-config SHA and expected live
minimum/maximum. It changes precisely one existing setting for each budget,
checks against physical RAM, orders sysfs writes safely, reads back, and writes
an exclusive private journal before applying. Default is read-only:

```sh
python3 arc_budget.py --max-gib 8 --min-gib 2 \
  --expected-config-sha256 REVIEWED_SHA \
  --expected-max-gib 24 --expected-min-gib 8 \
  --journal /PRIVATE/arc-trial.json
```

Add `--apply` for the live trial. After observing memory pressure and throughput,
rerun with the **then-current** expected live values, a new journal, and
`--apply --persist`. Persistence atomically updates only the two module options
and refreshes the running kernel's initramfs. It does not reboot the host or
change the bootloader, pool, compression, prefetch knobs or VM huge-page policy.
Verify live parameters, full config hash and presence of `etc/modprobe.d/zfs.conf`
in the generated initramfs. Other/older boot kernels need their normal initramfs
refresh before use; no host-reboot acceptance was performed in this round.

On failure, persistent config/initramfs refresh is recovered from the original
bytes. For deliberate rollback use the private original journal: restore the
full original config, raise max before raising min where required, read back
the original live values, and refresh the applicable kernel initramfs. Do not
overwrite unrelated edits without reviewing the current full hash. Re-evaluate
this budget after major VM allocation changes; it is not a universal ZFS default.

## Jellystat rebuild and rollback

`jellystat_policy.py` validates PostgreSQL 15, the reviewed digest-pinned
Jellystat 1.1.12 image, and the native procedure definition hash. Docker-local
connection data is read in memory, not logged. Defaults change only for the
Jellystat role **inside its own database**; other roles/databases/global
PostgreSQL defaults are untouched.

```sh
python3 jellystat_policy.py --journal /PRIVATE/statistics-before.json \
  --backup /PRIVATE/statistics-before.dump
# Reviewed application (includes exclusive pg_dump and archive-list check):
python3 jellystat_policy.py --journal /PRIVATE/statistics-before.json \
  --backup /PRIVATE/statistics-before.dump --apply --benchmark
```

The benchmark explicitly runs the existing native orphan-statistics procedure;
it can delete that procedure's normal orphaned statistics rows, not media or
Jellyfin library records. Without `--apply`, nothing is restarted or changed.
The tool cancels only matching same-role/same-database cleanup calls older than
20 minutes, then restarts only Jellystat so its connection pool adopts defaults.
The PostgreSQL container and other ARR services stay up. A caught apply failure
restores only the three prior settings and reconnects the statistics app.

For deliberate rollback, restore each of the three settings from the private
journal with native `ALTER ROLE ... IN DATABASE ... SET` or `RESET` where it was
unset, then restart only the app. Do not restore the whole statistics database
just to roll back a GUC. Role settings persist in the existing database across
container recreation; re-review the image/schema guard after an upgrade.
PostgreSQL `work_mem` is per operation, can multiply across queries, and is
**not** a fixed total allocation; 32 MB was sufficient for the measured plan,
and 64 MB provided no better plan. Do not raise it globally or to gigabytes.

## Enhanced native policy and search rebuild

`jellyfin_policy.py` validates Jellyfin 12.1 and Enhanced 12.7.0.0, reads its full
native plugin configuration and changes only `TagCacheServerMode`. It journals
privately, performs exact API readback, rolls back a caught mismatch, and does
not restart Jellyfin. Use the server's legitimate private API token:

```sh
python3 jellyfin_policy.py --url https://example.invalid \
  --token-file /PRIVATE/token --journal /PRIVATE/enhanced-before.json
# Add --apply only after reviewing the version and one-setting plan.
```

The native fallback uses the current user and visible cards; its existing batch
size/access filtering and rating/genre/quality features remain enabled according
to that user's settings. The global disk snapshot is retained by upstream for
rollback, but its in-memory cache and incremental maintenance are disabled by
the native policy. Restore the journaled full configuration through the same
plugin API if re-enabling; never publish its secrets. Re-evaluate this choice
against later upstream cache implementations instead of assuming the old
large-library policy is forever optimal.

For the search watcher, build Enhanced commit
`daf5b10c09d017941e29a79a0a45d0ab31c34abc` with these patches in order:

1. `patches/jellyfin-enhanced-12.7-tabs.patch`
2. `patches/jellyfin-enhanced-12.7-search-priority.patch`
3. `patches/jellyfin-enhanced-12.7-search-performance.patch`

Build the `jf12`/net10 target, retaining its existing native Tabs/request
integration and deploy **only** `Jellyfin.Plugin.JellyfinEnhanced.dll`. The
acceptance build used SDK image
`mcr.microsoft.com/dotnet/sdk@sha256:4beef5b8919dcaa2dc924233bd069257e883cc7a061e09088a97d152d6a48510`,
container build root `/src`, Release configuration and a bounded 2 GiB/two-CPU
build. Do not ship extra dependency DLLs, a net9 artifact, APK or root skin ZIP.

`enhanced_install.py` guards both exact before/after DLL hashes, server/plugin
activation and the visible-card policy. Default plan is read-only. Apply
privately backs up the DLL/full configuration, performs one Jellyfin stop/start,
verifies Active and unchanged full configuration, and restores the old binary
on caught failure. The accepted new DLL SHA is
`043af78aa281437a8d8b9eacb9a62996ab977e57fb138305104890e5498b677d`.
A different artifact/path/version needs review and a new pin; do not bypass it.
For rollback restore the saved DLL with Jellyfin stopped, start it, verify Active
and the unchanged private configuration. Only server restart, not Proxmox/LXC
reboot, is necessary. Unknown active playback requires the normal deployment
policy unless the user explicitly authorizes interruption.

The 30-second observer is a bounded slow-response repair, not arbitrary spelling
correction or a promise for an indefinitely unavailable backend. New rendering
cancels old animation frames; a disconnected page or section retires it early.
Owned Movies/Shows → Discover → Venom Not HD and current-user request/favourite
actions remain the contract. Test actual DOM order after a delayed response,
not merely a successful API search.

## Verification and retained boundaries

```sh
python3 integration/server/performance/test_arc_budget.py
python3 integration/server/performance/test_jellyfin_policy.py
python3 integration/server/performance/test_jellystat_policy.py
python3 integration/server/performance/test_enhanced_install.py
python3 integration/web-navigation/check-web-patches.py
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

The final authorized desktop reload returned 164 cards and 154 rating badges,
an approximately 2.14-second LCP observation and one 51 ms long task. Its tag
responses totalled approximately 27.5 KB, with no whole tag-cache request and
zero console errors (one warning). Earlier whole-cache parses exceeded 600 ms;
this is not a controlled cross-device percentage or a field responsiveness score.
Actual Web search was also tested with native item queries artificially delayed
seven seconds **only in the maintenance browser**: owned Movies still appeared
above Discover, followed by Venom Movies — Not HD. The interceptor was removed
in a finally handler; other users/server traffic was not delayed. Home order
and mobile-width layout were inspected separately.

The browser audit used real Chromium CLI/CDP profiling, resource timing,
long-task observations, UI snapshots and screenshots. Chrome DevTools MCP was
unavailable; this is not a Lighthouse/field-INP or formal multi-user benchmark.
Raw evidence remains private. Mobile wrapper clients can consume server-hosted
Web changes; a native Moonfin renderer is not rewritten by a Web/plugin update.
All users benefit from shared server pressure/query repairs, without broadening
their library or request permissions. No custom native app is necessary.

Physical HDMI DV7/FEL, audio lip-sync, episode-end behavior, extended provider
uptime and an unreachable original box remain separate acceptance boundaries.
Do not infer these from source preservation, grid loading or a web screenshot.

## Primary references used

- [OpenZFS module parameters](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html): live ARC controls and budget semantics.
- [PostgreSQL 15 resource consumption](https://www.postgresql.org/docs/15/runtime-config-resource.html): per-operation work memory, hash operations and multiplicative concurrency.
- [PostgreSQL ALTER ROLE](https://www.postgresql.org/docs/15/sql-alterrole.html) and [client defaults](https://www.postgresql.org/docs/15/runtime-config-client.html): database-scoped persistent settings and timeout behavior.
- [Jellyfin configuration](https://jellyfin.org/docs/general/administration/configuration/) and [troubleshooting](https://jellyfin.org/docs/general/administration/troubleshooting/): measured database/concurrency changes rather than blind cache/lock tuning.
- [Enhanced source at the reviewed pin](https://github.com/n00bcodr/Jellyfin-Enhanced/tree/daf5b10c09d017941e29a79a0a45d0ab31c34abc): native server-cache toggle, visible-card tag pipeline and bounded search observer.
- [Jellystat upstream](https://github.com/CyferShepard/Jellystat): statistics service distinct from playback/library state.
