# Restricted remote-appliance access

This policy accompanies one independently enrolled remote AM9. It does not
enroll devices, distribute keys, open public ports, install firmware, or replace
the tailnet's policy. All real profiles, ACL snapshots, identifiers, key material
and acceptance logs stay in private operations storage.

Reviewed cohort: CoreELEC22 Amlogic-no aarch64 nightly20260926, official repository
`service.tailscale`22.0.12.9, Tailscale1.102.4. Install through Kodi's matching
official repository. Never reuse another appliance's Tailscale state or host key.

## Files and deployment

- `firewall.py` → `/storage/.config/am9-tailnet-firewall.py`.
- `launch.py` → `/storage/.config/am9-tailnet-launch.py`.
- `20-private-access.conf` →
  `/storage/.config/system.d/service.tailscale.service.d/20-private-access.conf`.
- Root-owned mode0600 `/storage/.config/am9-tailnet-firewall.json` contains exactly
  `hostname`, `wifi_mac`, `admin_ipv4`, `media_ipv4`. Both peers must be distinct
  literal CGNAT-overlay IPv4 addresses. This is private per-device configuration.

Stop only the Tailscale service before initial policy installation. The firewall
refuses to apply around a running daemon. It tests both address families before
applying and alters only owned chains/interface-qualified hooks, preserving LAN
traffic and unrelated firewall state. IPv4 accepts ordinary key-only SSH from
one administrator and NFSv4/TCP2049 to one media peer; IPv6 and forwarding are
blocked. Established flows are restricted to those same peers/ports. It uses
`--noflush`, not a whole-firewall replacement. Cross-family atomicity is not
claimed; the overlay must remain stopped until both applications succeed.

The launcher requires the exact reviewed upstream startup hash. Amlogic's
`oe_setup_addon` reads modern Kodi settings incorrectly: only version2 is parsed
as text, while Kodi22 writes version4. The wrapper parses versions1–4 itself and
overrides only whitelisted addon values, without changing CoreELEC's global
loader or falsifying Kodi's XML version. It requires connect=true, an explicit
matching hostname, and disabled routing/exit-node options. Unknown formats or
source drift fail closed.

Persist these addon settings through Kodi: `ts_connect=true`,
`ts_auto_hostname=false`, `ts_hostname=<this appliance hostname>`;
`ts_accept_routes`, `ts_exit_node`, `ts_subnet_routes`, `ts_use_exit_node` false;
empty `ts_subnets` and `ts_exit_node_host`. The wrapper explicitly disables DNS
takeover, accepted routes and Tailscale SSH interception. Existing OpenSSH uses
the separately installed public key, with password authentication disabled.
It also disables Tailscale self-updates while retaining update notifications.

The local API must answer before startup proceeds. `up` has a30-second timeout;
offline but correctly enabled daemons remain alive to reconnect. Bounded
preference verification rejects a stopped/unsafe configuration. A service being
"active" is NOT acceptance: verify BackendState=Running, exact node identity/IP,
actual key-authenticated SSH and ordinary HTTPS after service restart and reboot.
The60-second restart delay prevents rapid error loops; unexpected addon updates
are deliberately not silently accepted.

## Tailnet control-plane prerequisite

Grants are additive. A narrow new grant cannot constrain a pre-existing allow-all
rule. Back up current policy and its ETag, inventory all devices/tags/subnet and
exit routes, preserve existing unrelated permissions, validate positive/negative
policy tests, then publish with `If-Match`. Abort/reconcile on conflict. Only then
assign the one distinct appliance tag. Never grant this box a server/admin tag.

Required effective access: administrator→appliance TCP22;
appliance→media peer TCP2049; no other appliance overlay initiation. Preserve
normal member/server traffic. A member-based migration must explicitly preserve
any existing subnet/exit workflows; do not paste a sample policy blindly.
Test other-peer→appliance SSH denial and appliance→server administrative/service
port denial live. Disable this appliance's node-key expiry only after narrowing
its identity; keep an explicit device-revocation procedure.

## Exact-peer remote original-media bridge

`media_forward.py` is a separate PVE-side helper, not a change to the existing
LAN NFS service.  It permits only this shape: one managed appliance sends TCP
2049 to the bridge's overlay address, NAT preserves that source and rewrites
only the destination to the existing LAN-only NFS listener.  The post-DNAT
INPUT exception requires the appliance source, the LAN destination, TCP2049,
and conntrack's exact *original* overlay destination.  This prevents a route
to the LAN address from becoming an unreviewed equivalent path.  All other
tailnet TCP/UDP2049 is dropped before the generic Tailscale INPUT accept rule;
IPv6 NFS is denied.

The private root-owned mode0600 bridge profile has exactly `bridge_hostname`,
`client_ipv4`, `overlay_ipv4`, and `backend_ipv4`.  The two overlay values are
literal distinct CGNAT IPv4 addresses; the backend is a literal local RFC1918
address.  If `tailscale0` exists it must own the configured overlay address;
at early boot it may be absent because interface-qualified rules are inert.

Deployment is deliberately ordered because legacy iptables cannot make filter
and nat updates one transaction: first verify the static TCP-only NFS listener;
then `--check` and `--apply-filter`; add an exact appliance-only read-only
`all_squash` export mirroring the existing fsid/crossmount options; and only
then `--apply-nat`.  Never add NFSv3, mountd, a wildcard listener, forwarding,
SNAT or MASQUERADE.  `--reconcile` first tests every plan and then makes that
same filter-before-DNAT order.

The `systemd/` templates are a reviewable persistence proposal: the timer and
normal boot oneshot reassert the guarded reconciliation, while Tailscale/Docker
post-start drop-ins ask systemd to run that independent oneshot again.  The
post-start request intentionally ignores a bridge-policy failure so it cannot
fail Docker or Tailscale.  Copy templates only with the matching reviewed
script/private profile and inspect parent unit semantics at the target release.

For rollback, turn Native mode off first so the client returns to authenticated
HTTPS, apply `--block-all` to cut even conntrack-retained authorized flows,
revoke the exact export, remove DNAT with `--remove-nat`, then remove the
filter hooks with `--remove-filter`; preserve LAN exports and unrelated
Tailscale rules.  A transport connect is not FEL acceptance: retain the separate
native-path/provenance, remote-throughput and physical display/audio gates.

## Update and recovery

Set Kodi's per-addon user-disabled-auto-update rule for `service.tailscale`,
alongside the already patched addons. Preserve firmware's manual-update policy.
On this reviewed Kodi build, `update_rules.updateRule=1` is the user-disabled
rule; if maintaining its database directly, stop Kodi, back up its database,
insert only the exact addon rule and restart. Do not assume the enum on a new
Kodi version. Review the addon script hash/platform/permissions, rerun tests,
and repeat restart/reboot/network checks before upgrading the pin.

Private same-device snapshots must include `.config`, addon settings/sources,
SSH authorized keys and `.cache/tailscale/tailscaled.state` (the enrollment
identity). This state is a credential: archives mode0600, directories0700,
verified off-device copy. Restore it only to the same recovered appliance, never
clone it into a second active device. A new device must enroll independently.

Rollback over LAN: stop Tailscale, restore its reviewed private settings/drop-in
and policies, then test. To remove private access entirely, revoke the enrolled
device and exact NFS export/grant together, stop/disable the addon, and remove
only this policy's hooks/chains. Disabling the Jellyfin account alone does not
revoke device-level NFS. Do not restore an old allow-all policy while leaving a
tagged appliance authorized. Returning a tagged node to user ownership requires
reauthentication, not merely deleting all its tags.

Run `python3 -m unittest discover -s integration/device-policy/private-tailnet`.
Runtime evidence and private profiles are not shipped here. Bell-house Wi-Fi,
WAN throughput and physical HDMI/FEL acceptance are separate from local tests.

## Primary references

- [Official CoreELEC Tailscale source](https://github.com/CoreELEC/CoreELEC/tree/coreelec-22/packages/addons/service/tailscale).
- [Amlogic settings loader](https://github.com/CoreELEC/CoreELEC/blob/coreelec-22/projects/Amlogic-ce/packages/mediacenter/kodi/profile.d/00-addons.conf).
- [Tailscale grant selectors](https://tailscale.com/docs/reference/syntax/grants)
  and [device identity](https://tailscale.com/docs/concepts/tailscale-identity).
- [Official device/tag/key-expiry API client](https://github.com/tailscale/tailscale-client-go-v2/blob/main/devices.go).
- [Tailscale1.102.4 settings implementation](https://github.com/tailscale/tailscale/blob/v1.102.4/cmd/tailscale/cli/set.go).
