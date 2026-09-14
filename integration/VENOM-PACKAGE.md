# Standalone Venom source package

The complete `plugin.video.venom.tv/` directory is included in this fork, not
just a diff against a private copy. Its four Python modules and window XML
represent the deployed add-on snapshot verified on the Ugoos on 2026-09-14.
This is source packaging; it does not publish an auto-update repository or APK.

## Offline verification

From a clean checkout, run:

```sh
python3 integration/check-venom-package.py
```

This checks the add-on's syntax and window navigation IDs, shared-favourite
logic, and server evidence/hide/restore rules. It does **not** claim to test
Kodi rendering/playback, every skin patch, or the stock Moonfin interface.
The broader integration checker has separate pinned-source/patch requirements.

## Another Kodi device

Use the same supported Kodi/CoreELEC and Arctic version, install IPTV Simple
Client, then configure that device's private gateway M3U settings locally.
Sign into the intended account in Jellyfin for Kodi. This add-on reads those
existing local settings; no provider account, Jellyfin token, userdata database
or private M3U URL is shipped here.

Install the complete `plugin.video.venom.tv` folder as a Kodi add-on and enable
it. Open it through Video add-ons to reach Live TV, Movies, Series and Favourites.
The Arctic Home Venom shortcut is a separate skin integration; this package
alone does not create or overwrite a device's home layout or audio settings.
The sidebar uses Arctic fonts/textures and was verified with Arctic Fuse 3.2.19.

The media server also needs the authenticated Live TV Categories service,
provider-ordered category data and curated collections. Without it, the live
browser falls back to the device's PVR groups. Shared favourites use the signed-
in Jellyfin user, not an administrator token. VOD matching requires the managed
Venom library paths; it will refuse ambiguous matches.

`patches/venom-live-categories.patch` is retained for old installed versions.
Do not apply it a second time to the complete source in this package.

## Server dependencies

The evidence/visibility scripts under `server/` include their policy dependency.
Their production paths, service wiring, recovery ledger and verification limits
are documented in `VENOM-REMAINING-WORK.md`. They are not a universal server
installer: review the media-server paths and private authentication helper before
deploying elsewhere. The default visibility command is dry-run.

Current-device installation must wait until the user turns the Ugoos on; do not
wake it just to synchronize files. The packaged browser already matches the last
verified deployed browser SHA256 recorded in `VENOM-REMAINING-WORK.md`.
