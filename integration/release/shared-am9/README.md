# Shared AM9 build and device parity audit

Habibi and Moustafa use one maintained repair release with separate local and
remote profiles. Shared fixes must be prepared and tested for both profiles;
account, network, hardware calibration and playback transport are not cloned.
The October 2 release `am9-shared-20261002.1` was installed on the remote AM9
on October 8. The original/local layer remains **prepared, not deployed**.
It is an additive software/configuration repair, not a firmware image, new-box
installer or unattended updater.

## October 8 remote deployment

The fresh remote inventory found CoreELEC22 nightly20261006 / Kodi22RC1 already
installed, with the exact reviewed 59-file starting source and zero drift.
The existing private profile passed hardware/account/transport guards. The five
planned files were installed while idle using one Kodi stop/start; the final
plan was empty and all 59 final hashes matched. No firmware, boot layout,
network, account, AV calibration, shortcut or keymap changes were made.
The boot ID stayed unchanged.

The six awake/OLED settings and eight CEC overrides still match. Current enum
labels retain Ignore/None meanings, and a bounded pathname-only trace captured
Kodi opening its CEC override successfully during the install restart. The
tracer detached. Canada regulatory state and 5 GHz Wi-Fi survived the intervening
OS boot. The remote's physical TV-off/on and HDMI/audio acceptance remain separate.
Forced screensaver activation reported ScreenSaverActive=true and DPMSActive=false;
SSH/Kodi stayed available and Back returned to Home. This checks screen hiding,
not a physical TV standby cycle or overnight uptime.

The replacement snapshot includes the device's own ConnMan/regulatory files,
Tailscale state, four bundled urllib3 dependency sources and nine SQLite online
copies. Its off-device checksum, all 59 addon hashes and every database quick
check passed. Recovery archives and profiles stay in the private operations
record. Ordinary snapshot retention remains three files.

Runtime Home/API checks confirmed newest-watch-first resume, newest-added-first
Movie/Series rows and 30 genuine IMDb ratings. Both `A Quiet Place` and
`Quiet Place` were submitted through the actual Kodi keyboard; the owned item
was returned, with separate Venom rows. Arbitrary spelling correction is still
not implemented (`quite` differs from `quiet`). The Combined dropdown can retain
a prior selected section. Selecting Movies also passed the on-device check:
the owned card was foregrounded with its IMDb7.5 badge. No new automatic
selector-reset algorithm was introduced.

This UI test also exposed an unused native-PVR startup wait on the remote HTTPS
cohort. The supported [remote startup setting](../../device-policy/remote-startup/README.md)
was applied and read back; it accounts for the local PVR cohort without disabling
its required functionality. Search mode and source integrity stay unchanged.

The current remote account receives 339 categories, including all 37 curated
groups with no empty curated group. This supersedes the October2 server outage
readback below; restoring those groups was not part of this box transaction.
Curated News category OK populated 45 channels and moved focus to the grid.
Remote Movies has 61 categories and Series has 40; each All titles route fetched
a bounded 160-title page plus its More entry and rendered 80 grid cards.
Repeated browser entry/exit and Stop/reopen cleared the window singleton.
A curated channel labelled 8K actually decoded H264 1920x1080/25fps:
first hardware frames in 6.46 s, frame counter 7→204 over 8 s,
with zero decoder/drop errors. This is a bounded decode test, not proof of8K,
HDR, visible HDMI quality or every provider channel. Another channel failed;
the server's two FFmpeg attempts both received upstream HTTP503. No capacity
failure or upstream403 was found in the bounded gateway log sample. The stream
failure was not repaired by the navigation overlay and remains a provider/server
availability limitation. No provider limits were changed.
The original box was unreachable on its LAN address and
remains pending for its own seven-file transaction.

## Audit findings

The original box was read live on October 2, with Kodi idle. Its 55 tracked
repair files had zero integrity drift, required tools/dependencies were enabled,
manual update protection was present, and no system services were failed.
The recent Kodi log sample contained none of the selected exception patterns;
that is not a guarantee of error-free playback. The remote box was offline.
Its October 1 inventory, private archive and recorded r2 source deployment were
used instead of presenting a reconstructed snapshot as a new device read.

| Repair or setting | Original box | Remote box | Shared release action |
| --- | --- | --- | --- |
| Home, search, intro, next episode, library sync, shared favourites | Maintained source present | Same common source, plus reviewed transport differences, in saved evidence | Preserve both; repeat current UI/playback acceptance |
| Bounded owned-library Discover index | Old unbounded bridge remains live | r2 installed | Port the same bounded bridge to the original |
| Rating visibility and indicator default | Older predicates/default | r2 installed | Make the repaired XML identical |
| Empty IPTV list and deferred grid focus | Older navigation | r2 installed; extended empty-list repair pending | Apply the same generic focus functions to both |
| IPTV playback lifecycle | Local PVR Stop/poll/Open | Remote HTTPS close-before-player | Keep these reviewed transport differences |
| Awake and OLED policy | Six live settings and CEC XML match | Six saved settings and CEC XML match | Not a missing transfer; live remote load/TV-off test remains |
| Backup dependency source | Broad rsync `packages/` exclusion | Python exclusion already corrected | Root the local rsync filter so bundled packages survive |
| Network recovery backup | ConnMan present; regulatory hint not selected | New ConnMan/regdomain selection not installed | Preserve each device's own network recovery files |

After applying the prepared changes to **private fixtures only**, the common
bridge and both repaired skin files were byte-identical. Common worker,
cancellation, favourite-mutation, rendering and local handoff contracts were
preserved. All remaining compared differences were reviewed transport files;
all six compared Home/search shortcut hashes agreed. Exact original55/remote59
source cohorts passed whole-manifest guards and a second, no-change plan.
Private live-update profiles were bound to their own saved account and hardware
identity. This does not substitute for a new remote inventory or physical tests.

The installed tool cohort includes Arctic3.3.1, Jellyfin-for-Kodi2.2.0+py3,
Home1.1.0, Venom1.3.1, KodiSeerr4.5, TMDbHelper6.17.4, SkinVariables2.2.5,
UpNext1.1.9+matrix.1, AudioOffsetManager2.1.0, SlyGuy dependencies0.0.30 and
trailers0.2.0, with InputStream/PVR binaries matched to each Kodi platform.
Binary versions need not be identical. The original OS remains the reviewed
hybrid20260922 build; the remote OS is standalone-SD20261001. Neither was rebooted
or upgraded during this audit.

Upstream's [Arctic manifest](https://github.com/jurialmunkey/skin.arctic.fuse.3/blob/master/addon.xml)
reports3.3.3 at review time. It requires a separate reviewed rebase of our3.3.1
patches, not a stock overwrite. [Jellyfin-for-Kodi releases](https://github.com/jellyfin/jellyfin-kodi/releases)
still list2.2.0 as latest. The official [TMDb Helper source](https://github.com/jurialmunkey/plugin.video.themoviedb.helper/blob/master/addon.xml)
and [Skin Variables source](https://github.com/jurialmunkey/script.skinvariables/blob/master/addon.xml)
match6.17.4 and2.2.5. A development branch version is not an accepted update
artifact; no blind dependency or nightly upgrades were performed.

## October 2 shared server gaps

At that audit, both accounts received302 provider categories but zero curated
collections. The old published file has37 groups and1413 IDs, none matching the
11841 current native live-channel IDs in the earlier full readback. A new
promotion attempt produces only7 groups/34 native channels; the publisher's
200-channel minimum rejects it, and the channel-checker service reports failure.
Removing that guard would publish a shrunken catalogue, not recover the requested
groups. Do not fix this by deleting channels, resetting favourites or manually
renaming client rows.

At that audit, the required server work was to rebind the full curated provider/
gateway identities to current Jellyfin IDs using exact, unambiguous mappings, preserve user choices,
validate all groups and ordering, then publish atomically with rollback. Check
both accounts and both clients afterward. This server repair is **not included**
in this box update. The October8 readback above now finds all37 curated groups;
do not continue reporting the historical zero-group result as current.

Jellyfin12.1 and Seerr were healthy during the read-only check. Exact import,
subtitle-publication, remote-native-manifest and request-search workers had
successful latest service results. Those checks establish scheduler/service
health, not a new real-download or subtitle end-to-end test. The existing tests,
finite-retry policy and targeted refreshes remain the maintained contracts.

## Repeatable read only inventory

Run from a reviewed checkout on the administration server:

```sh
python3 integration/release/shared-am9/capture.py \
  --target root@PRIVATE-ADDRESS --expected-hostname PRIVATE-HOST \
  --output /PRIVATE-0700-DIRECTORY/device.private.json
python3 integration/release/shared-am9/report.py \
  --local /PRIVATE/original.private.json --remote /PRIVATE/remote.private.json
```

Use `--host-key-alias` only for the existing verified SSH identity. Capture runs
read-only Python over SSH and creates a new0600 local evidence file in a0700
directory. It never serializes tokens, passwords, full addon settings or raw logs.
Inventories still contain private device/account identifiers and stay out of Git.
The numeric active Addons database selector deliberately excludes historical
`Addons33.pre-*.db` files; reading a backup database gave a false unpinned result
in the initial audit and is regression-tested. Missing settings, dependency
evidence or CEC files report unknown, not success.

## One release with separate installation profiles

Keep the `integration/release` and `integration/device-backup` directory layout
in the staging envelope. Historical R6/R7/search-priority/remote-originals
builders remain pinned; this layer imports their additive repair functions,
not the legacy root skin. `local_overlay.py` uses the same generic r2 and
empty-focus functions as the remote builder with `remote=False`, preserving
the existing local playback branch.

Create a private JSON profile per device with `cohort` (`local` or `remote`),
`hostname`, `wlan_mac`, `jellyfin_user_id` and `jellyfin_address`. Local requires
global Native1 and no remote marker. Remote requires Native0, its own
`remote_marker_sha256`, `snapshot_worker` path directly under `.config`, and
`snapshot_worker_before_sha256`. Reuse only that device's reviewed identity;
do not copy another profile or place real profiles in this repository.

```sh
python3 integration/release/shared-am9/install.py --profile /PRIVATE/device.json
# Explicitly authorize an idle deployment only after reviewing the plan:
python3 integration/release/shared-am9/install.py --profile /PRIVATE/device.json --apply
```

Default is no-write. The CLI checks actual hostname and WLAN hardware identity;
the plan checks account/server, transport marker, complete integrity manifest,
all touched source and the private backup worker. Identity, existing CEC/keymaps
and selected network inputs are protected read-only transaction inputs. Unknown
cohorts and symlinked/traversing paths fail closed. The original plan has seven
writes; remote has five. No userdata, account, network, boot file or database is
replaced. Backup policy is written before the remote worker.

Both use the same release ID. Each writes its own `.config/am9-shared-release.json`
receipt containing cohort and manifest hash, **not credentials or a claim of
physical acceptance**. A successful original deployment does not mark the offline
remote device updated. Keep its private rollout status pending until its own
fresh plan, deployment and acceptance pass. This is a paired release process,
not a deployed polling daemon or automatic push when a device wakes up.

Apply uses the existing idle-only transaction, private changed-file backup,
one Kodi stop/start, post-stop input revalidation and readiness check. It does
not reboot CoreELEC or restart networking. Caught failures restore originals;
power loss or SIGKILL still requires inspection and manual recovery. Roll back
while idle by restoring the changed files and addon manifest together; restore
or remove only that release's receipt according to `change-paths.json`. Never
restore the other device's settings, network or boot media.

## Tests and acceptance

```sh
python3 integration/release/shared-am9/test_local_browser.py
python3 integration/release/shared-am9/test_release.py
python3 integration/device-backup/test_local_overlay.py
python3 integration/release/ui-reliability/test_overlay.py
python3 integration/release/ui-reliability/test_remote.py
python3 integration/release/remote-catchup/test_remote.py
python3 integration/release/remote-catchup/test_installer.py
python3 integration/check.py
```

The new local runner exercises49 navigation/playback contracts; the remote
extended runner exercises80. Installer/report tests cover profile mismatch,
manifest drift, idempotency, receipt secrecy, unsafe paths, historical database
selection, unknown evidence and newly unexplained source differences. A real
rsync fixture confirms the rooted cache filter preserves bundled dependency
packages. Private saved-cohort tests additionally cover the complete deployed
file sets and real private worker transformations without contacting a player.

At the next authorized device update, capture a fresh inventory, inspect/retain
an off-device backup and complete the relevant checklist in
[the catch-up record](../../REMOTE-AM9-CATCHUP-2026-10-02.md): cold/warm Home,
owned search with/without article, Discover, rating badges, IPTV section/category
navigation, empty response, Back during loading, A→B→A and Stop→reopen, movie/
episode playback, shared favourites, next-episode/intro, seeking, subtitles and
HDMI audio/DV. Check a new backup for dependency and device-specific network
recovery files. Recheck the remote5GHz band and native regulatory loader at an
authorized reboot. Confirm TV off/on leaves the box reachable with unchanged
boot ID; screensaver black is not system suspend.

Firmware stays separately reviewed: hybrid SD/SSD versus standalone SD are not
interchangeable. Preserve manual updates and the existing Tailscale startup
repair. Do not use a generic auto-nightly workflow to make OS versions equal.

For every future generic change, prepare both profiles under a new shared
release ID, update both source pins/tests and record applied/pending/accepted
per device. A justified transport or hardware difference must remain explicit.
