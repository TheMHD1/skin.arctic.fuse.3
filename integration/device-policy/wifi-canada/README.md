# Canadian AM9 Wi-Fi regulatory setting

Use only for a device physically operating in Canada. This is a supported
CoreELEC configuration setting, not a driver/firmware replacement or a way to
bypass country-specific radio limits.

On the reviewed CoreELEC22 nightly20261001 image,
`/usr/lib/udev/rules.d/60-iw-regdomain.rules` invokes
`/usr/lib/iw/setregdomain` when the wireless PHY is added. That script sources
`/storage/.cache/regdomain.conf` and runs `iw reg set "$REGDOMAIN"`.
The supplied file therefore belongs at `/storage/.cache/regdomain.conf`.
Preserve any existing file privately before making a reviewed country change.
For the current boot, `iw reg set CA` applies the same country hint without an
OS reboot. Allow the driver to settle before inspecting the channel table.

October1 remote AM9 diagnosis: firmware config contained `ccode=DE`, global
country was00, channels149–165 were disabled, and the configured Bell SSID was
connected on2.4GHz channel6 at144Mbps. The supported CA hint enabled the upper
channels; a scan discovered the same SSID on channel157 and the device roamed
there automatically. Observed5GHz receive link rate1080.8Mbps, transmit960.5Mbps.
These are negotiated radio rates, not an internet or media throughput benchmark.
The device's own password, ConnMan service and network identity were unchanged.
No BSSID pin, firmware binary, NVRAM power table or router configuration changed.

Validate `iw reg get`, `iw phy phy0 info` (channel availability),
`iw dev wlan0 link` (actual band/rate) and sustained media playback. The persistent
file was installed and its native loader reapplied successfully; reboot-time
acceptance is separate and must not interrupt a viewer merely to test it.

This native cache file is outside the old custom snapshot worker's selected
cache paths. The [October2 backup migration](../../device-backup/README.md)
explicitly selects it and the device's own ConnMan configuration. That migration
was installed October8, and the resulting archive was verified off-device.
That fresh boot already had country CA and5GHz receive/transmit negotiated rates
of1080.8/960.5Mbps, without a network change during the addon rollout. Do not assume older archives
contain this setting or the Bell provisioning file.
For a rebuild in Canada, merge this policy alongside the existing awake/audio/
remote-access policy. For another country, use its correct supported country code.
Rollback restores the previous file and reapplies its previous valid country
setting; no addon, Kodi database or firmware rollback is needed.

Reference: [Linux Wireless iw regulatory-domain commands](https://wireless.docs.kernel.org/en/latest/en/users/documentation/iw.html).
