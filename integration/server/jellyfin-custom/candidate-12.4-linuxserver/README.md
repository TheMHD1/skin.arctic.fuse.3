# Jellyfin 12.4 LinuxServer operational candidate

This candidate preserves the deployed LinuxServer S6 `/init`, `/config` data
layout, `/dev/dri` hardware-device contract and bundled FFmpeg behavior. Its
base is pinned to LinuxServer Jellyfin `12.4ubu2604-ls57`, AMD64 manifest
`sha256:50b431edbea22045f97c5d662b4ab22a48e0aeab1e186702ec2a02bf70dd0eec`.
An isolated container verified `/usr/bin/jellyfin --version` as `12.4.0.0`.

Build a private context outside the repository with the pinned patched 12.4
server assemblies, 12.4-guarded Library Experience DLL/meta, generated exact
12.4 Web `dist`, and the tested Enhanced, KodiSyncQueue (including LiteDB) and
IntroSkipper plugin directories. Build this `Dockerfile`; do not use a floating
tag or combine 12.1 assemblies with this base.

The initial, historical local test image
`habibi/jellyfin:12.4-linuxserver-candidate-20261028` has image ID
`sha256:32be8aa42dad787c84b67a30a35e08f924cbb7f89e3f8707cfe857a9a7d72cc0`.
The real synthetic publication fixture passed its Movie/Episode discovery,
identity-conflict, Arabic subtitle replacement/VTT, durable outbox and
no-global-scan assertions against this image. It is not a production release:
perform the complete stopped-config snapshot and rollback procedure documented
in the sibling candidate README before any controlled canary.

## Historical all installed-plugin blank runtime gate

The full-feature, blank-config candidate image is
`habibi/jellyfin:12.4-linuxserver-allplugins-candidate-r5`, immutable local ID
`sha256:024764b09599bc10c1284a80abc5a970e7a6b6c91dc5b8ed4c0158f10eda68f9`.
It loaded AniDB, Anime Filler Marker, Artwork, Chapter Segments Provider,
Fanart, Intro Skipper, Jellyfin Enhanced, Kodi Sync Queue, Library Experience,
custom Live TV Categories, Local Intros, Moonbase, Playback Reporting and
Reports in a new config with no production XML, cache, database, account or
token. Anime Filler's required `HtmlAgilityPack.dll` was included beside its
declared primary DLL. Jellyfin Enhanced initialized and completed its startup
task; its empty-config CDN warning did not prevent plugin load.

## Current complete candidate

Use the final all-feature r2 image and exact inputs in [BUILD.md](BUILD.md),
not either historical image above. Its full Web bundle preserves owned Home,
search, category browsing and all native Live TV tabs. A real authenticated
browser on a blank isolated configuration rendered Home, the category view,
Guide and Channels, and navigation between them; this does not prove provider
streaming, populated production rows or physical-client playback.

The retained Moonbase source is plain reviewable source, independently checked
against its exact 201-file manifest. The digest-pinned SDK builder passed 341
tests and verified every emitted artifact. Its test project explicitly excludes
six retained historical test files whose 10.10 fake is incompatible; this is not a
claim to have run those tests. See BUILD.md for the reproducible artifact pin
and mandatory complete stopped-config rollback procedure.

## October 28 earlier production attempt and recovery

The reviewed all-feature candidate started successfully with all 20 expected
plugins. Database continuity passed: accounts, permissions, API keys, display
preferences and watch-history identities were retained. The owner explicitly
accepted only the known inherited-rating-cache migration difference; this did
not authorize changes to account policies or other continuity checks.

The later operational acceptance validator incorrectly treated Docker's
reordering of unchanged bind strings as a runtime configuration change. The
guard therefore restored the entire pre-upgrade configuration and exact 12.1
image. Full file-content, ownership, permissions, ACL/xattr and hardlink checks,
all six database-continuity groups, and native/public health passed after
recovery. Production is back on 12.1; this is not a successful 12.4 deployment.

The reviewed correction canonicalizes only the `HostConfig.Binds` list order.
Every complete bind string, option and duplicate remains bound, and every
other runtime field remains strict. A future attempt must capture a fresh
healthy baseline using that corrected validator; never reuse the old raw-order
hash or start another promotion before the previous recovery is terminal.
Retain verified external recovery archives and reclaim only independently
verified redundant working copies before rechecking capacity.

## October 28 corrected production deployment: accepted

The subsequent corrected retry completed successfully. Production now runs
the reviewed all-feature Jellyfin `12.4.0` image from [BUILD.md](BUILD.md), with
all expected plugins active, the runtime/mount/device contract verified,
database continuity accepted, and native plus public HTTPS health passing.
The prior paragraph describing production restored to 12.1 is the historical
rollback state, not the current deployment.

The full verified pre-upgrade recovery archive and exact prior image/plugin/Web
references remain retained privately. Accounts, permissions, API keys and
display preferences matched the captured baseline. Watch-history coverage was
preserved, with only the reviewed native conflicting-row harmonization; no
unexpected rows were accepted. The owner-approved inherited-rating-cache
migration difference was the only separate opt-in, not a policy reset.
Paused publishers were restored before the executor recorded success. This
acceptance does not imply that an offline remote Kodi device was updated or
that physical TV/audio and every client playback case were tested.
