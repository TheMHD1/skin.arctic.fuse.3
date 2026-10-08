# Arctic startup for remote Jellyfin playback

The remote AM9 uses authenticated Jellyfin HTTPS for Venom, not local native
PVR channels. On October 8, Arctic3.3.1 repeatedly displayed **Waiting for PVR**
while `System.HasPVRAddon=true` and both PVR channel lists were empty. This could
obstruct Home and Search even though their server requests had finished.

Arctic's native `Startup.DisableWaitForLoad=true` removes this unnecessary
startup gate. Widgets still load asynchronously. No addon is disabled, source
patched, firmware changed, or network/account copied. Search mode and Discover
remain unchanged.

## Profile applicability

Configuration amendment `am9-ui-policy-20261008.1` accompanies the
[shared repair release](../../release/shared-am9/README.md). `skin-settings.json`
records both profiles: apply the setting to the remote HTTPS cohort; the local
PVR cohort has no change because it actually uses native channels. Do not infer
that the local appliance received another update. This policy is not a daemon
or an automatic update mechanism.

Reviewed runtime: Arctic3.3.1, SkinVariables2.2.8, TMDbHelper6.17.5,
CoreELEC22 nightly20261006 / Kodi22RC1. Recheck the installed
`shortcuts/skinvariables-startup.json` and
`1080i/Includes_SkinSettings.xml` after an upstream skin update: the former gates
on this boolean, and the latter exposes the same native setting. A future
unrecognized setting is not permission to edit a whole settings file.

## Application and rollback

First bind the intended device to its private profile and verify the complete
addon integrity manifest. Require idle Kodi. Keep a private backup of
`userdata/addon_data/skin.arctic.fuse.3/settings.xml` and the previous runtime
boolean. On the box, apply the single native setting through the local Kodi
event client:

```sh
kodi-send --action='Skin.SetBool(Startup.DisableWaitForLoad)'
```

Read back `Skin.HasSetting(Startup.DisableWaitForLoad)` with JSON-RPC
`XBMC.GetInfoBooleans`. Also verify the persistent skin settings contain
`startup.disablewaitforload=true`; use the actual native XML serialization, not
a complete file copied from another device. Do not overwrite live skin settings
with a shell/XML rewrite. Retain the normal idle snapshot and verify its copy
off the appliance. Rollback a previously false value with
`kodi-send --action='Skin.Reset(Startup.DisableWaitForLoad)'`, then read it back.

Enter Home and Search repeatedly, submit a query through the virtual keyboard,
and ensure Startup/PVR no longer blocks navigation. Server list success alone
does not validate this UI behavior. The October8 remote readback and actual
keyboard tests passed after application; firmware and boot identity were
unchanged. Physical TV power cycling remains separate from this policy.

Run `python3 integration/device-policy/remote-startup/test_policy.py` to check
the exact setting and local/remote applicability contract. This fixture is not
a Kodi runtime test.
