# Guarded next-episode handoff

This release guard preserves the existing Jellyfin-for-Kodi Episode-to-Up-Next
handoff on both accepted AM9/CoreELEC clients.  It is intentionally not a skin
change and does not replace Kodi's playlist, Up Next's prompt, or either
client's Jellyfin transport.

## What it protects

The pinned Jellyfin 2.2 source patch prepares adjacent-episode metadata as soon
as an Episode starts.  Up Next owns the 120-second prompt, cancellation, and
the three-episode still-watching boundary.  At end of file it sends the
existing authenticated `plugin.video.jellyfin_play_action` back to Jellyfin for
Kodi.  Kodi/Jellyfin therefore retain their normal direct-play, Dolby Vision
profile-7 local path, remote HTTPS/add-on transport, and per-device account
selection.

The important release correction is that `jellyfin_kodi/player.py` is now a
hashed builder output and a guarded installer input.  Previously the patch was
applied to the temporary build tree but the file was omitted from the payload;
the behavior could be lost by a later otherwise-valid cohort update.

## Contract

- normal Episode EOF: Up Next may invoke the next item once;
- explicit popup cancel or stop: no automatic next item is injected by this
  layer;
- final episode: the patch returns a completed handoff with no adjacent item,
  avoiding retries/loops;
- missing current item in an adjacent response: the handoff remains retryable,
  rather than claiming success;
- non-Episodes do not enter the Episode handoff;
- only the exact Jellyfin `2.2.0+py3` source pin and reviewed output hash are
  accepted.

## Build, test, and candidate deployment

From the repository root:

```sh
python3 integration/release/next-episode/test_contract.py
python3 integration/release/kodi/build.py --output /tmp/habibi-kodi-payload
python3 integration/release/kodi/test_release.py /tmp/habibi-kodi-payload
```

The generated payload is the candidate artifact.  A coordinator must first
verify both boxes are idle and have a current private integrity manifest, then
run the existing guarded installer in plan mode on each device, review that the
only new relevant replacement is
`addons/plugin.video.jellyfin/jellyfin_kodi/player.py`, and explicitly apply it
per the shared release procedure.  Do not copy settings, database files,
profiles, logs, or credentials between devices.

Physical acceptance on each client: play an ordinary non-final episode through
EOF; cancel an Up Next prompt and let the current episode finish; explicitly
stop; and play a season finale.  Confirm no duplicate starts, no automatic play
after cancel/stop, and no final-episode loop.  Confirm the local client still
uses its original P7 path and the remote client its normal authenticated
transport.

Up Next itself is a separately managed add-on.  Any version change must be
reviewed and recorded before its auto-update is allowed to become the cohort
baseline; this source guard deliberately does not overwrite user settings or
the add-on.

## Managed Up Next baseline

The reviewed cohort is upstream `service.upnext` **v1.3.0** at commit
`a7cadd1b0f706c41335323da30f2079e09d4f3a9`.  This is a real upstream tag,
not an untagged automatic update.  Compared with v1.2.3 it makes library
episode popups faster, tolerates incomplete episode details, closes a stale
popup when another episode starts, and contains new popup error containment.
Those changes are compatible with the existing Jellyfin event handoff and are
preferable to a rollback.

`upnext_policy.py` validates the non-personal behavior that must remain stable:
automatic advance, a 120-second prompt, Back/cancel preserving the current
episode, no playlist ownership conflict, and the existing three-episode
Still Watching boundary.  The boundary is deliberately preserved; it is not
evidence of failed EOF autoplay.  Change it only after a user decision, since
setting it to `0` removes the confirmation entirely.

## Live-test state guard

Do not use a real household episode as a disposable test fixture.  Before any
authorized live probe, capture the server `UserData` (`Played`, `PlayCount`,
`PlaybackPositionTicks`, and `LastPlayedDate`) **and** the local Kodi resume /
playcount fields.  `state_guard.py` defines the required three-way comparison:
restore only when the current state is exactly the state left by the test.  A
different current state is a possible concurrent user action and must block an
automatic restore.  The snapshot and profile are private artifacts, never
repository files.  A candidate with nullable `LastPlayedDate` is ineligible:
Jellyfin's nullable update DTO intentionally skips null and cannot faithfully
clear a test-created date.  Timestamp formatting is normalized to UTC
microseconds for comparison, but no timestamp is ever invented or rounded for
a write.
