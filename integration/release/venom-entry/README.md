# Paired Venom Home-menu repair

`am9-shared-20261008.4` follows the paired performance release. It applies the
same one-field Arctic repair to local native-PVR and remote exact-Jellyfin
cohorts; it does not copy accounts, networks or boot layouts.

## Cause and portable fix

The explicit Venom TV Home route still required `PVR.HasTVChannels`. Remote
Venom uses the signed-in Jellyfin account over HTTPS and deliberately does not
depend on a native Kodi PVR catalogue. Its addon and catalogue could work while
the actual Home tab remained greyed out. Direct `RunScript` tests bypassed that
tab and therefore did not prove the normal user entry worked.

`overlay.py` changes only the enable predicate of
`Home_ControlList_Item_1107` in the exact reviewed Arctic3.3.1 `Includes_Home.xml`:
the explicit Venom label requires the enabled Venom addon and Home toggle;
other/native-PVR labels still require the Home toggle, PVR addon and TV channels.
It does not enable an absent addon, alter provider permissions, disable PVR or
change playback/favourites. Tests evaluate all32 combinations of the actual
Kodi expression, unknown source/duplicate-anchor rejection, both installers,
protected input guards and idempotency. Existing browser regressions remain
mandatory. A Home-menu fix alone is not proof of reliable playback transitions.

## Build, installation and rollback

This historical layer is included in the current
[short transaction release](../library-transactions/README.md). Use that latest
installer for the complete shared build; the commands below reproduce this
individual layer.

Stage `integration/release` and `integration/device-backup` preserving their
relative layout, with only the intended appliance's existing private profile.
The installer composes the complete preceding shared/UX/performance release
for a pending original device. Do not install the legacy root skin ZIP.

```sh
python3 integration/release/venom-entry/install.py --profile /PRIVATE/device.json
python3 integration/release/venom-entry/install.py --profile /PRIVATE/device.json --apply
```

Default is no-write. Whole source-manifest, account, hardware, transport, parent
receipt and private keymap/CEC/network guards remain. Apply refuses active or
paused playback, privately journals changes, performs one Kodi stop/start and
requires an empty final plan. It does not reboot/update CoreELEC or replace
user databases. Firmware needs its separate device-specific review.

| Cohort | Inventory | Whole manifest SHA-256 |
| --- | --- | --- |
| Local native PVR | 57 files | `c7a0e103d03c5b8a739c8bdb88f14e6530e6be3b52f977aa236420e18932e977` |
| Remote Jellyfin HTTPS | 61 files | `69e97deb4258457c3ad25c31fa676bd566d01212ded269d40ef6a3f845236fec` |

Keep the installer transaction directory. Roll back while idle with Kodi
stopped: restore its recorded changed files and prior manifest together, remove
only newly created files from `change-paths.json`, start Kodi, verify the prior
cohort and repeat Home-menu entry. Never restore another appliance's userdata.
Caught errors use transaction rollback; power loss/SIGKILL needs inspection.

```sh
python3 integration/release/venom-entry/test_entry.py
python3 integration/release/venom-entry/test_install.py
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

## Device acceptance

Both complete private saved cohorts reproduce their output and a no-change
second plan. Remote source installation completed October8; actual Home-menu
and transition acceptance is recorded in the
[companion OS/UX runbook](../../REMOTE-AM9-UPDATE-2026-10-08.md).
The original local box remains prepared, not deployed. Publication does not
automatically deliver changes to an offline appliance.

The acceptance checklist must use the real Home tab, not only direct scripts:
cold/warm entry, Home→reentry, modal launch refusal, Back during a request,
categories/movies/episodes/pagination/favourites, same-channel selection,
A→B→A, live→owned movie, owned movie→live, background-video Home→Venom and
stop→reopen. Confirm fresh advancing decoder frames, responsive GUI input,
stable Kodi PID/restart counter and stable OS boot ID. Provider errors and
physical HDMI/audio/HDR checks remain separate from navigation success.
