# Persistent AM9 5 GHz Wi-Fi selection

This optional device policy selects the configured household network on 5 GHz,
retains its existing ConnMan credentials and corrects a late Canadian radio
initialization defect. It does not force a missing access point to exist. If the
configured 5 GHz network is unavailable, it preserves administrative connectivity
instead of permanently stranding a remote appliance.

## Playback diagnosis and deployment

On October 12, the remote AM9 booted on 2.4 GHz at a negotiated rate of about
144 Mbps. Three authenticated 8 MiB HTTP range reads from the affected episode
measured 38.9, 53.6 and 52.6 Mbps. The 4K HDR remux averages 41.19 Mbps; those
short samples leave little headroom for variable bitrate and Wi-Fi contention.
Insufficient delivery headroom is a likely explanation for the reported cache
warning, not a proven reconstruction of the original on-box failure.

Server playback records showed an episode stopping around 17 minutes and a
subsequent start stopping at zero after approximately 20 seconds. No matching
server FFmpeg failure was present. A short decode near the stopping position
completed with HEVC warnings; this is not a whole-file integrity check. The
pre-power-cycle Kodi session log was unavailable. Current Kodi authentication
and HTTP range delivery passed using the addon-style Authorization header.

The global country setting was CA, but the driver's upper 5 GHz channels were
disabled. Reapplying the supported country hint enabled them. Neighbouring
5 GHz networks then became visible, but the configured household SSID remained
visible only on 2.4 GHz, including a targeted active SSID scan. A bounded trial
restored the prior frequency selection after failing to establish 5 GHz.

The policy, timer and private identity profile are installed on the remote AM9;
hashes, service execution, timer enablement and the missing-AP fail-open path
passed. Successful 5 GHz roaming, sustained episode playback and boot-time
acceptance remain pending until the household 5 GHz access point is available.
No firmware, Jellyfin account, cache size, AV settings, addon source or media
file was replaced. The same generic policy is available for the local cohort,
but it is not deployed there; its own network profile and radio acceptance are
required. Publication does not deliver it to another appliance automatically.

## Policy behavior

The helper checks the exact device hostname, radio MAC and household SSID from
a private profile. It discovers the supplicant interface rather than assuming
a fixed D-Bus object number. Country must match the appliance's physical
location. The existing native `regdomain.conf` remains the first boot policy.

The timer starts 20 seconds after boot and performs a bounded check once per
minute. An existing 5 GHz connection needs only inexpensive property reads and
an idempotent `freq_list` update. It never scans or disconnects that healthy
connection. A recreated ConnMan network receives the restriction again.

On 2.4 GHz, an active scan for the exact configured SSID runs at most once per
five minutes, without automatic scan-driven roaming. Only a visible matching
5 GHz access point can trigger a roam. The helper chooses the strongest matching
access point and restricts selection to legal, driver-enabled 5 GHz channels;
it does not persist one BSSID or assume the router always uses channel 157.
A failed handoff restores the original frequency selection and requests a
reconnect. A previously owned restriction is released when its 5 GHz AP is
missing, retaining remote access. Other saved networks are not edited.

The late Canada hint is reapplied only when upper channels are disabled, with
a 30-minute cooldown to prevent repeated radio resets. No firmware/NVRAM power
tables, radio power levels or country restrictions are bypassed. No password
or administrator API token is supplied to or logged by this policy. Status
messages omit household identities and suppress duplicate missing-AP warnings.

## Installation and verification

Reviewed runtime: CoreELEC 22 nightly 20261008, its existing ConnMan,
wpa_supplicant D-Bus API, `busctl --json=short`, `iw` and Python 3. This is an
optional configuration policy, not a replacement for the paired addon source
installer. Preserve local-PVR versus remote-HTTPS account and transport settings.

1. Run `python3 test_policy.py`. Preserve previous target files, enablement state
   and the appliance's `regdomain.conf` in a private off-device backup.
2. Verify hostname, radio MAC, physical country and the installed OS/tooling.
   Derive the private profile from `profile.example.json`; never commit it.
3. Copy `policy.py` to `/storage/.config/scripts/am9-wifi-5ghz.py`, mode 0755,
   and the two unit files to `/storage/.config/system.d/`, mode 0644. Install
   the private profile as `/storage/.config/am9-wifi-5ghz.json`, mode 0600.
   Verify source hashes after copying; never replace unknown existing files.
4. Run `systemctl daemon-reload` and
   `systemctl enable --now am9-wifi-5ghz.timer`. Run the service once and check
   its journal, `/run/am9-wifi-5ghz.json`, `iw dev wlan0 link`, country/channel
   availability and the next timer firing.
5. Verify the exact SSID on a 5 GHz frequency, HTTP throughput comfortably
   above content bitrate, sustained playback and a normal authorized reboot.
   Test missing-AP/failed-roam recovery before claiming remote readiness.

All `.config` policy files are covered by the maintained device snapshot roots;
keep the private profile and own network credentials out of public manifests.
Runtime cooldown state intentionally lives in `/run` and resets at boot.

## Rollback

Stop and disable `am9-wifi-5ghz.timer`, then stop its service. Restore the prior
target files and timer enablement from the private backup, or remove only these
four newly installed policy targets if they were originally absent. Reload
systemd. A native reboot/ConnMan network recreation drops the transient
supplicant frequency restriction; without reboot, restore that network's
recorded original `freq_list` through D-Bus and request `Reconnect` only if
needed. Preserve SSH/Tailscale and the native country file. The policy never
rewrites passwords, firmware, Kodi userdata or the paired addon integrity receipt.

## References

The supported country hint follows the
[Linux Wireless iw documentation](https://wireless.docs.kernel.org/en/latest/en/users/documentation/iw.html).
Interface country, scans, roaming and network properties use the existing
[wpa_supplicant D-Bus API](https://w1.fi/wpa_supplicant/devel/dbus.html).
Hardware policy still limits legal channels; neither interface bypasses it.
