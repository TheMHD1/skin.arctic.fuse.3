# Jellyfin 12.1 server customizations

This is the source-preservation entrypoint for server changes used by every
client, separate from the Kodi skin. It contains **source patches and tests**,
not a database, API key, plugin bundle or blindly deployable replacement image.
Jellyfin-derived code remains GPL-2.0-or-later under its upstream licence;
retain upstream licensing when building/distributing it.

## Exact source and rebuild

Upstream: `https://github.com/jellyfin/jellyfin.git`, revision
`ee91c75e777da41a9c4f4855e70adc604fbf2ef8` (12.1).
`prepare.py` checks out that exact revision in a **new** directory, checks and
applies the patches, and adds their tests. An optional `--source /path/to/git`
uses a local repository as the object source without copying its working tree.
No original server checkout or production service is modified.

```sh
python3 integration/server/jellyfin-custom/prepare.py /tmp/jellyfin-reviewed-source
cd /tmp/jellyfin-reviewed-source
dotnet test tests/Jellyfin.Server.Implementations.Tests/Jellyfin.Server.Implementations.Tests.csproj -c Release --filter 'FullyQualifiedName~BaseItemRepositoryPlayedVersionTests|FullyQualifiedName~BaseItemRepositoryResumeDedupTests' --nologo
dotnet test tests/Jellyfin.Naming.Tests/Jellyfin.Naming.Tests.csproj -c Release --filter 'FullyQualifiedName~EpisodeVersionExclusionTests' --nologo
dotnet build Jellyfin.Server.Implementations/Jellyfin.Server.Implementations.csproj -c Release --nologo
dotnet build Emby.Naming/Emby.Naming.csproj -c Release --nologo
```

Use the .NET 10 SDK required by upstream `global.json`. Build outputs are
generated artifacts, not committed DLLs. A rebuilt DLL need not have an old
binary hash unless the entire compiler/dependency environment is reproduced.
The deployed September 22 server-implementation DLL was
`9c31c8f008a90fcde2b536c8ef73397a92c17f0c9be15f0f1eb7391fbce193f3`.

### Patch contract

| File | Purpose | Required configuration |
| --- | --- | --- |
| `continue-watching.patch` | One resumable episode per series, selected by newest real playback activity; preserves rewinds, per-user permissions and paging | None; changes the shared Resume API, not history |
| `../../patches/jellyfin-12.1-onepace.patch` | Exact directory opt-out from episode multi-version collapsing (includes tests) | `HABIBI_JF_EPISODE_VERSION_EXCLUDED_DIRECTORIES=One Pace` (semicolon-separated exact directory names) |

The preparer reuses the existing episode-exclusion patch instead of keeping a
second copy. Other custom server plugins have their own source/patches: see
[the customization index](../../CUSTOMIZATIONS.md) and
[12.1 category/sync recovery](../../VENOM-RECOVERY-2026-09-18.md).

## Deployment and rollback

These changes were deployed and tested on September 22; preparation here is
not a fresh claim of live acceptance. Continue Watching passed eight scoped
tests and a read-only 26-account API audit with no duplicate series or errors.
It does not mark anything watched or delete watch progress.

Build a candidate image from the matching maintained server image, adding only
the two reviewed assemblies. The pinned baseline recipe is
`../maintenance-20260918/jellyfin-Dockerfile`; add the server implementation DLL
alongside its existing naming DLL. Preserve OpenCL/QSV dependencies, mounted
plugins, web integration and all private configuration. Never replace a newer
server's assemblies with 12.1 binaries. Rebase source and rerun tests first.

Before a deployment, retain the prior image/compose and a consistent private
database/config backup. Test ordinary Resume queries with `MediaTypes=Video`,
episode rewinds, library restrictions and Next Up separately. Roll back the
image first; restoring the database unnecessarily would lose recent viewing
progress. Private production backup locations remain in the operations record.

## Colour/tone-mapping configuration fix

This fix is **configuration, not another DLL patch**. On the tested Intel
QSV server, preserve QSV encoding and enabled tone mapping, and set
`PreferSystemNativeHwDecoder=true` in the full encoding configuration returned
by Jellyfin's authenticated `/System/Configuration/encoding` API. Read and
privately back up that full object first, change only this field, submit the
full object, and read it back. Do not POST a one-field replacement or copy a
different server's device paths/bitrate settings. No API token belongs here.

The observed P5 colour failure used QSV decoding without Dolby Vision
reshaping. Native decoding enabled the proper tone-map route. P5, P8.1,
HDR10, SDR and text/PGS subtitle server-transcode samples were checked. This
is not a universal preference for every GPU or proof of every direct-play
display chain. Recheck decoder/filter logs and a decoded sample after future
FFmpeg/Jellyfin upgrades. Roll back the saved encoding configuration if needed.
