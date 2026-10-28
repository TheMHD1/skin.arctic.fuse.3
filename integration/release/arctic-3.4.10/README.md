# Arctic Fuse 3.4.10 source candidate

This is a version-specific, source-only rebase from the managed Arctic 3.3.1
feature set to upstream Arctic Fuse 3 `3.4.10` commit
`7206a2a1d2f9d62a025c495619a9e07d53dd2be7`. It deliberately does not modify
the legacy root skin, a Kodi profile, or either AM9.

The overlay ports the complete shared Home/search feature chain:

- owned → Discover → Venom ordering in combined and wall Search modes;
- owned/Venom selectors in Standard mode, which has no upstream Discover mode;
- the ratings provenance/indicator layout;
- KodiSeerr request, folder, and playable-leaf actions; and
- the new upstream configurable Hub architecture, with an explicit conditional
  Venom entry that leaves all non-Venom Hub use upstream-native.

It requires SkinVariables `>=2.2.9`, and upstream Arctic requires TMDb Helper
`>=6.17.9`. The candidate pins a review target of TMDb Helper `6.19.1`
(`61917067582cb860ace3c3013a80eea17724c637`): this is newer than Arctic's
minimum, but it has a materially larger dependency set and is **not** approved
for a blind device installation. A fresh read-only verification found both
clients already run TMDb Helper 6.19.1 with its reviewed dependencies; it must
still be preserved and staged rather than reinstalled blindly. The authoritative
October 28 live audit already verified SkinVariables 2.2.10 and ran its exact
engine in isolated staging: owned selectors were IDs 502/503 and Venom was
504/505. Do not substitute the stale local 2.2.3 audit checkout for that
reviewed engine. This candidate must not be installed until the exact TMDb
Helper artifact and required modules are staged and verified. The live Jellyfin Kodi, Venom,
next-episode, passthrough, DV/P7 and private transport overlays are outside
this skin-only builder and must remain in the paired AM9 release.

## Build and validate

Use a clean checkout pinned exactly to the commit above. `fetch.py` creates one
deterministically; test execution requires its path explicitly, so a fresh CI
clone cannot silently skip the actual overlay tests. The result contains
only changed skin files, a SHA256 manifest and a reproducible binary patch.

```sh
stage=$(mktemp -d)
python3 integration/release/arctic-3.4.10/fetch.py --output "$stage/upstream"
ARCTIC_FUSE_3410_SOURCE="$stage/upstream" \
  python3 integration/release/arctic-3.4.10/test_overlay.py
python3 integration/release/arctic-3.4.10/test_dependencies.py
ARCTIC_FUSE_3410_SOURCE="$stage/upstream" \
  python3 integration/release/arctic-3.4.10/test_stage.py
python3 integration/release/arctic-3.4.10/build.py \
  --source "$stage/upstream" \
  --output /PRIVATE/arctic-3.4.10-candidate
```

Before an artifact enters either private device stage, inspect the exact ZIP
without installing it:

```sh
python3 integration/release/arctic-3.4.10/dependencies.py \
  --artifact /PRIVATE/plugin.video.themoviedb.helper-6.19.1.zip
```

The verifier rejects a wrong ID/version, changed requirements, unsafe ZIP
members and ambiguous addon roots. It does not prove CoreELEC/Kodi runtime
compatibility or install anything. The real generator has already passed with
the copied 2.2.10 engine, but must be repeated after the actual private
local58/remote62 staging copies are assembled. Record the exact staged ZIP
SHA256 and every required module's installed version in each private profile.

## Paired guarded runtime plan

`stage.py` is the only preparation executable in this directory. It refuses an
unmarked profile, requires a copied private staging profile with the reviewed
3.3.1 skin, validates the pinned TMDb artifact, writes a complete staged 3.4.10
skin, and snapshots the old skin plus protected add-on data and generated
template inputs. It has no `--apply` mode and cannot target a live device:

```sh
python3 integration/release/arctic-3.4.10/stage.py \
  --source /PRIVATE/clean-arctic-3.4.10 \
  --profile-root /PRIVATE/copied-local58-profile \
  --tmdb-artifact /PRIVATE/plugin.video.themoviedb.helper-6.19.1.zip \
  --output /PRIVATE/local58-arctic-3.4.10-stage
```

The resulting schema-2 `stage.json` pins the copied cohort's complete 3.3.1
skin tree, existing Habibi resume receipt and complete transformed 3.4.10
tree. A target whose bytes differ is rejected rather than treated as a matching
cohort. Older schema-1 private stages are evidence only and must be rebuilt.

`install.py` remains **plan-only**: public `--apply` exits before mutation.
Its reviewed future adapter takes `/storage`, invokes the canonical
library-transactions parent plan to verify every manifest-listed source and the
full paired identity before inspecting Arctic, then repeats that guard after
idle Kodi has stopped and before the recoverable directory switch. Normal use
reads hostname and WLAN MAC from local CoreELEC files; caller assertions are
not trusted.

The eventual paired transaction must
build the complete pinned upstream skin plus this overlay **once per cohort**,
then take private rollback snapshots before one idle Kodi restart. Each snapshot
must include the entire prior Arctic addon, both Arctic/SkinVariables addon-data
trees, TMDb Helper addon-data tree, `guisettings.xml`, and all generated
`script-skinvariables-generator-includes*` files. Never replace or merge a
different device's profile, account, Tailscale state, menus, keymaps, CEC,
network, Jellyfin transport, DV/P7 or audio settings.

Preflight must retain the existing local58/remote62 identity and full manifest
guards, prove the local Native and remote HTTPS profiles separately, verify
SkinVariables/TMDbHelper/module artifacts before switching skins, and generate
templates only in a copied private staging profile first. The real generator
must finish with XML-valid generated selector routes for combined, wall and
standard modes. Only then may the existing paired transaction framework receive
a separately reviewed 3.4.10 skin payload. Physical UI, HDR/DV/TrueHD and
Next Up acceptance remain distinct for each appliance.

Before any device deployment: run the SkinVariables generator against a
separate staging profile (never the active profile), compare the generated
combined/wall/standard selector include IDs with the current device's actual
menu shape, then perform the paired guarded deployment and physical UI/audio/
HDR acceptance. This builder is intentionally not an installer.

### Real generator gate

SkinVariables 2.2.10 does not provide an output-directory, skin-root or profile
override. `buildtemplate` reads and writes `special://skin`, specifically
`1080i/script-skinvariables-generator-includes-{skinuser}.xml`; `no_reload=true`
does not change that. Do not call it in the normal Kodi session.

`generation_probe.py` is the guarded executable for this runtime gate.  It is
plan-only by default.  An explicit `--apply` first runs the complete paired
source receipt plus local hostname/WLAN-MAC/Jellyfin identity guards, rejects
active playback, and repeats those guards after normal Kodi has stopped.

It creates a new private child of `/storage/.arctic3410-generation/`, not a
copy of live Kodi userdata.  That HOME contains only the candidate skin, its
recursive non-service dependency closure, a minimal active-skin setting, and
the reviewed staged skin/SkinVariables menu inputs.  It excludes Jellyfin data,
repositories, services, Tailscale, credentials, sources, keymaps and live GUI
settings.  Candidate 3.4.10 additionally needs private reviewed trees for
`resource.images.arctic.weather` 1.0.4 and
`resource.images.arctic.splash` 1.1.0; their exact full-tree hashes are pinned
by the tool.  It never accepts an arbitrary ZIP or fetches/installs dependencies
itself.

For `--apply`, direct `/usr/lib/kodi/kodi.bin` is launched in a unique transient
`systemd-run` unit, never through `kodi.sh`.  The unit enforces read-only
`/storage/.kodi` and `/flash`, permits writes only to the private HOME, and uses
`PrivateTmp`, `ProtectSystem=strict` and `NoNewPrivileges`.  Before invoking
SkinVariables, it requires released JSON-RPC/event ports and runs a nonce-bound
proof script inside that transient Kodi process.  The script uses
`xbmcvfs.translatePath` for `special://home`, `special://profile`, and
`special://skin`, then atomically writes a schema-checked receipt through the
translated private profile path.  The host rejects stale/non-regular receipts,
wrong nonces, unknown JSON keys, and every mapping outside the private tree.
This replaces an unreliable debug-log heuristic without relaxing the mount
sandbox. A new sandbox Addons database initially marks discovered copied addons
disabled, so the probe first starts only built-in Estuary. It dispatches Kodi's
supported `EnableAddon(id)` built-in only for audited private plugin/script
members of the closure, then `LoadSkin(skin.arctic.fuse.3)`, through the
loopback Event Server. It polls Kodi JSON-RPC only for the resulting enabled
state and active skin; it never blocks that RPC handler with synchronous enable
work, copies an Addons database, or changes a live database. The probe
snapshots/removes only private
generated includes, requires fresh nonempty XML containing every managed
owned/Venom selector route, then stops only its own unit. It proves the exact
transient unit is dead before restarting normal Kodi; if that proof fails,
normal Kodi deliberately remains stopped instead of competing for port 9090.

The October 28 `d01` local runtime attempt did **not** generate XML: synchronous
`Addons.SetAddonEnabled` did not reply before its RPC deadline, and its delayed
owned-unit cleanup briefly blocked normal Kodi's JSON-RPC port. Normal Kodi was
then restored active and idle; the remote device was plan-only and was not
applied. Neither is generation acceptance. The corrected event/builtin
activation and exact-unit cleanup path require a fresh paired runtime probe
before any skin transaction or physical UI acceptance. The CLI captures `kodi-send` helper
chatter and emits one JSON receipt, with the apply result nested under `result`.

Example read-only plan:

```sh
python3 integration/release/arctic-3.4.10/generation_probe.py \
  --storage-root /storage \
  --stage /PRIVATE/local58-arctic-3.4.10-stage \
  --profile /PRIVATE/local58-profile.json \
  --runtime-home /storage/.arctic3410-generation/local58-run-UUID
```

Do not add `--apply` until the reviewed dependency root has been staged and the
plan has passed.  Generated output still requires selector/action review before
any Arctic directory transaction; this probe is not a skin or firmware installer.
