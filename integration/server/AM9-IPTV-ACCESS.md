# AM9 IPTV access recovery

For Dispatcharr 0.31.0, the local native-PVR appliance must be permitted by the
persistent `CoreSettings` row keyed `network_access`. Valid XC credentials can
still be rejected when the appliance's current address differs from an old
exact-host allowlist. Native PVR then loses its playlist/categories even though
the server and Kodi custom sources are healthy.

## Diagnosis and guarded repair

Verify the device's SSH host key, account and interface MAC against its private
profile before trusting a new lease. Compare the actual playlist/account request
from the box with the server's request-IP policy. Check the appliance's own
saved credentials in memory without logging its URLs or passwords. A metadata
HTTP200/authentication result is not live channel acceptance.

Back up the current row as a private mode0600 file in persistent server data.
Use a locked database transaction to append only the verified literal device
IPv4 `/32` to `value.XC_API.allowed_networks` and
`value.STREAMS.allowed_networks`. Preserve all other fields, entries and access
groups. Save through the normal Django model so its settings-cache invalidation
signals run. Do not modify `UI`, `HDHR` or `M3U_EPG`, grant a subnet, raise provider
capacity, bypass authentication or restart the container unnecessarily.

Read back the normal effective settings and verify positive XC/stream access,
negative UI/other-group access and denial of unrelated addresses. Test actual
playlist fetching on the appliance, native PVR groups, **Arctic Home → Venom**,
category artwork/grid, channel decoding, channel switching, stop/Home and reopen.
Keep private before/applied records and deployment evidence outside the fork.

Verify a router-side reservation pairs this device's own Wi-Fi MAC with the
approved current address. An existing exact reservation needs no mutation or
renewal. Conflicts require explicit review; do not overwrite another device's
lease. Never infer the correct household router from an overlapping private
subnet: require the managed router's exact host key and identity first. A future
Ethernet/private-route change needs its own reviewed identity/address policy.

## Acceptance and cohort boundary

October 12 local acceptance: playlist/account HTTP 200, all 58 shared source hashes
unchanged, 303 native groups, actual Home-route category grid/artwork, two native
channels with advancing 1080p hardware decoder frames and zero reported decoder
errors, stop/Home and reopened Home route. The existing correct Wi-Fi reservation
was verified without router changes. This did not reinstall addons or firmware.
The [separate NFS startup repair](native-mount-recovery/README.md) restored library
sync file access rather than suppressing its missing-file dialog.

The paired addon release remains `am9-shared-20261008.7`: these are persistent
server/network configuration repairs, not a new mismatched client source cohort.
The remote appliance retains account-scoped Jellyfin HTTPS Venom; do not add its
home-router address to the local native-XC allowlist or clone the local PVR
profile. No remote client changes/acceptance are claimed by this repair.

## Updates and rollback

Preserve the persistent Dispatcharr settings row and the private DHCP identity
record during server/network updates. Recheck the upstream schema/cache signals
before using this procedure with another version. Restore only the two touched
access lists under a locked transaction using the reviewed private before record;
do not overwrite intervening administrator changes or restore the whole database.
Removing an address will intentionally revoke that device's native IPTV access.
