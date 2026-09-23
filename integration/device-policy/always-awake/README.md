# Always-awake CoreELEC with independent TV power and OLED protection

Configuration-only policy for the local AM9 Pro, applied September 23, 2026 on
CoreELEC 22 nightly20260922 / Kodi22Beta2 revision
`3de1f35efd63b69ad2e6cd0bb8d6f637c9d92f4d`. No boot media, kernel, Android,
audio passthrough, picture-processing or addon source changes are needed.

## Diagnosis and intended behavior

The live idle shutdown and display-sleep timers were already zero. No CEC
override existed. The installed `system/peripherals.xml` defaults
`standby_pc_on_tv_standby` to `13011`, which its own English strings identify as
Suspend. Thus TV standby can suspend Kodi despite the idle timers being Off.
The previous loss of HDMI was not captured live, so this is a demonstrated
configuration cause, not proof excluding every possible HDMI/firmware fault.

The box should stay running when the TV/JBL are off. It must not wake the TV
on screensaver exit or Kodi startup, nor send TV standby as Kodi stops.
CEC remains enabled for ordinary navigation/volume; hardware wake options,
AVR routing and other unspecified settings remain unchanged. TV power is now
independent: select its HDMI input manually if needed instead of relying on
Kodi's automatic active-source switching. Explicit Kodi reboot/power-off remains
available; no sleep-target masks, logind overrides or scheduler changes were made.

The **black screensaver after three minutes** replaces Dim. It keeps HDMI output
and CoreELEC running while hiding static UI. Disable the paused-video Dim
override and the music exception, so paused pictures and static audio screens
also receive the selected screensaver. Normal video playback does not invoke
the idle screensaver. Kodi's own modal-dialog exceptions may still force Dim.
This reduces static-image exposure; it is not a guarantee against OLED burn-in.
Leave the TV's own OLED protections enabled.

## Portable settings and guarded application

`kodi-settings.json` contains exact global setting IDs and typed values. Apply
through Kodi JSON-RPC `Settings.SetSettingValue`, then read each back with
`Settings.GetSettingValue`. Keep a private before-value JSON and guisettings.xml
backup. Do not overwrite guisettings.xml while Kodi is running. The settings
take effect live, without stopping a current video.

`cec-settings.xml` contains only the intended peripheral overrides, **not a
complete device configuration**. In the reviewed build, live English labels
confirm `36028=Ignore`, `231=None`, and `13011=Suspend`.

1. Audit the installed `system/peripherals.xml`, English strings and adapter
   identity; version guards and enum meanings must be rechecked after updates.
2. Back up the entire private `userdata/peripheral_data` directory. Stop Kodi
   before merging peripheral XML, or its runtime state may overwrite edits.
3. Resolve the actual settings file; do not blindly use this template's name.
   This box reports one AOCEC adapter named **HDMI**, VID/PID0000:0000, with no
   pre-existing `cec_*.xml`. The exact Kodi source explicitly supports the
   legacy `cec_HDMI.xml` filename if its physical-location file does not exist.
   It was seeded at `userdata/peripheral_data/cec_HDMI.xml` on this exact cohort.
   Other devices, existing files or multiple adapters require a reviewed merge,
   not creation of competing overrides.
4. Merge the listed IDs only, preserving addresses, language, volume, controller
   and other settings. Restart Kodi, verify the actual XML load, then recheck
   global settings through RPC. Do not merely assert a file exists.
5. Confirm the CEC adapter still registers, normal Kodi/Jellyfin functionality
   returns, and there are no failed system services. Test TV off/on and idle/
   paused screensaver behavior physically. A sleeping TV is okay; the box should
   remain reachable with unchanged boot ID.

The local acceptance used a short, pathname-filtered `strace` at Kodi startup
and observed a successful `O_RDONLY` open of the installed CEC override. The
trace detached afterward; no tracer, resident watchdog or polling service was
installed. Screen policy persisted through Kodi restarts.

## Verification and known limitation

The CEC override load and all six global setting readbacks passed. No system
reboot was needed. The configuration does not need a patched OS image or an
addon fork and resides on persistent `/storage` across normal OS updates.
Forced screensaver activation reported `System.ScreenSaverActive=true` with
`System.DPMSActive=false`; HDMI mode stayed 1080p60, SSH and Kodi remained live,
and `Input.Back` returned to Arctic Home. This verifies the black-screen/sleep
distinction without pretending to be a full three-minute idle or OLED panel test.

During verification, directly invoking `ActivateWindow(peripherals)` crashed
this Kodi build in `CPeripherals::GetDirectory` from the peripherals dialog.
Kodi recovered, and this direct-dialog automation route was abandoned. Do not
use it as a configuration/verification shortcut. This record does not claim the
underlying dialog crash is fixed or that the normal Settings path was tested.
The private crash record is retained; raw logs never belong in this fork.

Physical TV-off/on acceptance **passed**: the owner turned the TV off, then on,
and confirmed Kodi was already visible without unplugging the AM9. Boot ID was
unchanged, Kodi stayed active, and kernel suspend counters showed success=0,
fail=0. One SSH attempt briefly failed with no route; connectivity recovered and
there was no recorded system suspend/reboot, so it was not labeled a sleep event.
This is a short TV-cycle test, not overnight certification. Forced screensaver
activation alone is not proof of a full three-minute idle timer or of the panel's
burn-in protection.

## Rollback

Stop Kodi and restore the backed-up peripheral configuration (or remove only
the newly introduced override if none existed). Restore the six prior global
values through JSON-RPC after restarting Kodi. Do not replace unrelated settings
or another box's network/profile data. This policy never requires restoring boot
files, flashing Android or changing SD/SSD storage identifiers.

## Sources

- [Reviewed CoreELEC Kodi peripheral defaults](https://github.com/CoreELEC/xbmc/blob/3de1f35efd63b69ad2e6cd0bb8d6f637c9d92f4d/system/peripherals.xml)
- [Reviewed settings-file identity and legacy fallback](https://github.com/CoreELEC/xbmc/blob/3de1f35efd63b69ad2e6cd0bb8d6f637c9d92f4d/xbmc/peripherals/devices/Peripheral.cpp)
- [Reviewed TV standby Ignore handler and libCEC flags](https://github.com/CoreELEC/xbmc/blob/3de1f35efd63b69ad2e6cd0bb8d6f637c9d92f4d/xbmc/peripherals/devices/PeripheralCecAdapter.cpp)
- [Kodi power-saving settings](https://kodi.wiki/view/Settings/System/Power_saving)
- [CoreELEC CEC controls; device coverage varies](https://wiki.coreelec.org/coreelec:ce_cec)
