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
`>=6.17.9`. The candidate pins TMDb Helper `6.19.2` source commit
[`3a515987b0405d6e2298081edb71f8ab3099ecff`](https://github.com/jurialmunkey/plugin.video.themoviedb.helper/commit/3a515987b0405d6e2298081edb71f8ab3099ecff)
through official repository commit
[`1fd8db862c63066c2bd51df3183f2839874c9fff`](https://github.com/jurialmunkey/repository.jurialmunkey/tree/1fd8db862c63066c2bd51df3183f2839874c9fff/omega/zips/plugin.video.themoviedb.helper).
This is newer than Arctic's
minimum, but it has a materially larger dependency set and is **not** approved
for a blind device installation. Upstream did not create a `v6.19.2` tag, and
later nexus commits still declare themselves 6.19.2; the version string is
therefore never accepted as provenance. A fresh read-only verification found
both clients already run the exact 715-file payload from the pinned official
commit, with only derived `__pycache__/*.pyc` files in addition. It must still
be preserved and staged rather than reinstalled blindly. The authoritative
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
  --artifact /PRIVATE/plugin.video.themoviedb.helper-6.19.2.zip
```

The accepted artifact is the official
[`omega` ZIP](https://raw.githubusercontent.com/jurialmunkey/repository.jurialmunkey/1fd8db862c63066c2bd51df3183f2839874c9fff/omega/zips/plugin.video.themoviedb.helper/plugin.video.themoviedb.helper-6.19.2.zip),
SHA-256 `686a0f412a3183ea46c00b958e526e4b3e76bb44a902bea1aa305aa23b112560`.
Its compression-independent 715-file payload hash is
`f59cd113967da3c2ad6c20d7eca853d73948a716339ea18d9c419967f8e8881d`.
The verifier rejects any other ZIP bytes or payload, a wrong ID/version,
changed or additional imports, unsafe members, symlinks and ambiguous roots.
The 6.19.1-to-reviewed-6.19.2 source diff is the official
[`v6.19.1...3a515987` comparison](https://github.com/jurialmunkey/plugin.video.themoviedb.helper/compare/v6.19.1...3a515987b0405d6e2298081edb71f8ab3099ecff).
The verifier does not prove CoreELEC/Kodi runtime compatibility or install
anything. The real generator has already passed with
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
  --tmdb-artifact /PRIVATE/plugin.video.themoviedb.helper-6.19.2.zip \
  --output /PRIVATE/local58-arctic-3.4.10-stage
```

The resulting schema-3 `stage.json` pins the exact TMDb source commit,
repository commit, ZIP, payload, full import set and copied live payload along
with the cohort's complete 3.3.1 skin tree, existing Habibi resume receipt and
complete transformed 3.4.10 tree. The plan repeats the live 715-file payload
check before and after Kodi stops. It tolerates only cache-tagged `.pyc` files
inside `__pycache__` when the corresponding reviewed `.py` source exists. A
target whose source bytes differ is rejected even if it still reports version
6.19.2. Older schema-1/schema-2 private stages are evidence only and must be
rebuilt for both cohorts.

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
disabled. The current **unaccepted candidate design** therefore uses two
private-only phases: (1) start built-in Estuary in the newly-created HOME only
long enough for Kodi itself to discover the staged closure and create its fresh
`Addons33.db`, then prove that exact transient unit is gone; (2) while no Kodi
process owns that private database, verify its Piers schema and integrity and
atomically set `installed.enabled=1, disabledReason=0` for every and only the
audited closure row. The second transient Kodi start then dispatches only the
noninteractive `LoadSkin(skin.arctic.fuse.3)` builtin and polls the whole
closure. It never copies, reads, or changes the live Addons database.

Runtime activation is proved by the nonce-bound script's exact
`special://skin` mapping, not the saved `lookandfeel.skin` preference.
Kodi's [Settings RPC](https://github.com/xbmc/xbmc/blob/master/xbmc/interfaces/json-rpc/SettingsOperations.cpp)
and GUI skin property read that saved preference, while the
[LoadSkin builtin](https://github.com/xbmc/xbmc/blob/master/xbmc/interfaces/builtins/SkinBuiltins.cpp)
loads a skin directly. A real isolated October 28 probe loaded the candidate
but safely failed a former saved-setting check because it still said Estuary.
Normal Kodi was restored and no skin was installed. The corrected probe keeps
the stronger in-process home/profile/skin mapping proof before generation;
wrong or stale runtime mappings still prevent every generator call.

This is deliberately not a generic Kodi database editor: it rejects a missing,
symlinked, uncheckpointed, malformed, wrong-version, or incomplete private DB;
it rejects a closure outside the staged audited IDs; and it performs the one
private update inside a SQLite transaction. Its first phase has the existing
bounded RPC readiness check; phase two retains the existing bounded generation
budget. It is neither a retry loop nor a blind timeout increase.

The October 28 `d01` local runtime attempt did **not** generate XML: host-side
synchronous `Addons.SetAddonEnabled` did not reply before its RPC deadline, and
its delayed owned-unit cleanup briefly blocked normal Kodi's JSON-RPC port.
Normal Kodi was restored active and idle; the remote device was plan-only and
was not applied. The superseded `df0` event-action candidate is not accepted:
Kodi's documented `EnableAddon(id)` builtin prompts for a GUI confirmation.
The subsequent `f810` local private-script attempt is also not accepted: the
script began recursive enablement but stalled before its receipt or XML; normal
Kodi was restored and the remote remained plan-only. The two-phase DB design
above is source/test work only until a separately reviewed, fresh isolated
runtime probe proves it end-to-end. It is not a skin transaction or physical UI
acceptance. The CLI captures `kodi-send` helper chatter and emits one JSON
receipt, with the apply result nested under `result`.

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
