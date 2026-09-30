# Remote AM9 standalone-SD update — September 30, 2026

Status: deployed and verified headlessly, with owner-authorized reboot. This
supersedes the remote device's September26 OS version, not the original local
AM9's separately maintained hybrid-SD/SSD procedure. No Android flash, profile
clone, addon replacement or server change was made.

## Reviewed upstream

- CoreELEC22 Amlogic-no aarch64 nightly20260926 → nightly20260929.
- CoreELEC build `f30e977a4b5d94d6a6f6eae35efb903c7fa8f4c0`.
- Kodi22Beta2 → Kodi22RC1, revision `0661a5d74edc384f443b17c9467c1f5efa9ec337`.
- Kernel remains5.15.196, with the September29 build. This remains a nightly,
  not a stable release or a promise of regression-free future updates.
- Source: [official Amlogic-no nightly listing](https://relkai.coreelec.org/?dir=Amlogic-no/ce-22).
  It lists KodiRC1, Amlogic driver changes and a PGS subtitle fix. These release
  notes do not prove physical playback benefits on this headless appliance.

Observed downloaded tar SHA256:
`df2e48836e34cecd08a6266847c68d5675ed9260aef9d28d98773fea9da31bda`.
KERNEL SHA256:
`b68ade5a3c8713020ab9ba337c95b3c6b8379087832c59b6534a93c91553fb35`.
SYSTEM SHA256:
`e7122648374ac623f1d7f1755dcc74b1cf00c1d01ad389ce5f962f020169e66c`.
Embedded MD5 checks passed too. Local fingerprints/checksums detect corruption;
they are not an upstream cryptographic signature.

## Preservation and deployment method

1. Read the remote parity and private-access/original-P7 records. Verify the
   exact appliance identity, NICs, SD partition UUIDs, standalone mounts, source
   boot hashes, free space, empty update directory and idle Kodi. Never substitute
   this procedure for the local hybrid updater.
2. Capture private before-values/source hashes and make a SQLite-consistent
   Kodi/configuration snapshot that includes this device's Tailscale state and
   bundled dependency packages. Verify the archive and copy it off-device.
3. Unpack the official target on the maintenance host. Compare its kernel ABI,
   AM9Pro device tree, Dolby loader, updater, Kodi API manifests and CEC enums.
   On this pair the device tree, loader/updater, all Python/GUI/binary interface
   manifests and CoreELEC addon repository22.0.12 were unchanged. The version4
   addon-settings startup wrapper for Tailscale remains required.
4. Stop Kodi, snapshot boot/config files and verify an off-device copy. Transfer
   the complete tar outside `.update`, verify its exact reviewed hash, then move
   it atomically into `.update` and request a normal reboot. Do not interrupt
   power. No raw block-device writing or firmware/image substitution was used.
5. Verify the running build and exact installed KERNEL/SYSTEM hashes, same SD
   mounts, empty `.update`, Dolby module load and live Kodi/Tailscale services.
   Compare before/after settings and source; investigate any difference.

All4018 files inventoried across the six custom addons were unchanged; all59
files in the deployed integrity manifest still match. Home/skin shortcuts,
account credentials and identity, remote-only Venom marker, Bell provisioning,
audio/refresh/cache/UpNext configuration, CEC and OLED/always-awake policy,
original-P7 opt-in, key-only SSH and private-access policy were preserved.
Two raw-file hashes differed: Jellyfin refreshed `DateLastAccessed`, and Kodi
reserialized Arctic's XML. Explicit semantic comparisons proved every other
connection field and every skin setting unchanged. Do not silently exempt
whole files from preservation checks because they contain runtime fields.

Firmware remains configured for manual updates. User-disabled addon update
rules for Arctic, Jellyfin, KodiSeerr and Tailscale remain in place, as do
Tailscale's self-update restriction and daily idle backup timer. A new firmware
or addon version still requires review; do not blindly reuse the private script
with a substituted filename. Other devices need their own private guards and
identities, never copied state from this box.

## Acceptance performed

- Normal boot returned on LAN/Tailscale; key-only SSH works, private preferences
  pass, Kodi/Tailscale restart counts are zero and no systemd units failed.
- Nine SQLite quick_checks passed. No new MMC/I/O failure was observed.
- No custom-addon errors or Python tracebacks were observed. Two XKB
  missing-Compose locale messages remain; no unrelated configuration was
  changed to suppress them.
- Dolby module loads with the same pre-existing cross-build symbol warnings;
  this update did not remove those warnings or prove physical FEL decoding.
- Current account and Seerr authentication work over verified public HTTPS.
- Actual Kodi Movies/Shows and library-search routes return populated results.
  Continue Watching is latest-watch-first; Movies/Shows are newest-added-first.
  Ratings bridge returned IMDb scores for all30 sampled owned movie cards.
- IPTV category endpoint, one bounded channel lookup/exact identity, provider
  genres/VOD pages/posters and shared-favourites queries passed. No full provider
  channel scan or physical live-channel switching was performed.
- HTTPS movie byte-range returned206/65536bytes with TLS verification and no
  redirect. Actual Kodi VFS original-P7 selection/read succeeded for a movie
  and two episodes; forced transcoding still declines the original-file route.
  No playback/history was started or mutated by these media probes.
- Maintained integration checker,17 private-tailnet tests,13 remote-native
  tests and all5 release playback tests against the reviewed payload passed.
  The main checker has five explicitly optional/skipped fixture cases; this is
  not a claim that every possible integration fixture ran on the new OS.

The owner explicitly does not want to connect HDMI now. Physical LG/JBL
picture/audio, FEL/HDR signaling, seek/lip-sync and TV/CEC behavior remain
pending, as does throughput on the eventual remote-house connection. Headless
network/file tests must not be represented as physical AV acceptance.

## Recovery and rebuild

The private operations record retains exact-device updater/audit scripts,
before/after evidence, fresh boot files and SQLite-consistent userdata backups;
off-device recovery copies are access-controlled. Never publish those archives,
credentials, SSH keys, Tailscale state or real device profiles.

For a bootable regression, review a normal downgrade to the preserved prior
tar and assess DB migration compatibility before restoring userdata. If the
device cannot boot, attach its own SD to a maintenance host, verify its UUIDs
and restore its saved matching boot-file set without formatting storage.
Restore databases only with Kodi stopped; never combine old DBs and new WAL/SHM.
Restore private identity only to the same appliance. The exact old-source
updater is not an unguarded rollback script.

Custom rebuild sources remain the [remote parity chain](REMOTE-AM9-PARITY-2026-09-26.md),
[original-P7 layer](release/remote-originals/README.md) and
[private-access policy](device-policy/private-tailnet/README.md). Nothing in
this OS-only update replaces those addons or expands private network grants.
