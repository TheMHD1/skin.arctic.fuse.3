# Arctic Fuse + Jellyfin integration source

Personal, non-commercial integration fork of jurialmunkey's Arctic Fuse 3.
Upstream credits and licensing remain intact. This is not an official Kodi,
Jellyfin or Arctic distribution.

Start with [the customization inventory](integration/CUSTOMIZATIONS.md) for
the fixes, required versions and tested/pending status. It covers the Kodi/Arctic
experience and the paired Jellyfin/IPTV server changes.

- [Build and guarded update tooling](integration/release/README.md)
- [New Ugoos commissioning](integration/SECOND-UGOOS.md)
- [Update, rebase and rollback procedure](integration/UPDATING.md)
- [Server Continue Watching and colour configuration](integration/server/jellyfin-custom/README.md)
- [Dolby Vision compatibility-service source](integration/server/dovi/README.md)

**Do not install the repository-root ZIP as the current device release.** The
root skin tree retains the earlier 3.2.19 baseline; current deployed Arctic
3.3.1 uses the version-specific maintained patch and reviewed overlays. The
release tooling is an exact-cohort update, not a blank-device firmware image.

Source, tests, patches and redacted examples belong here. Passwords, API tokens,
real device profiles, databases, media and rollback backups stay private.
Changes must include a regression, documentation and a refreshed source hash
inventory before they are recorded as preserved. Verify a clone or source archive:

```sh
python3 integration/release/verify-preservation.py
```

The September 22 local-device r6 changes were accepted; the remote-device
overlay remains source-tested but not deployed. The CoreELEC update remains
held. Source preservation never implies permission to reboot or update a device.
