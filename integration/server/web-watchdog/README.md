# Jellyfin web-only failure watchdog

The October28 audit found the existing timer's script probed localhost even
though Jellyfin's port was published only on the host's LAN address. Both
probes therefore returned connection errors and the watchdog never checked the
real Web UI. Set `JELLYFIN_WATCHDOG_URL` to the **actual private listener** in a
root-owned0600 environment file, and reference it in the existing unit with
`EnvironmentFile=/etc/habibi/jellyfin-web-watchdog.env`. Never publish that
deployment file or change Jellyfin's binding to work around the watchdog.

`watchdog.sh` retains the existing narrow web5xx/API200 policy and15-minute
cooldown. It serializes invocations and repeats both probes before restarting
only the Jellyfin container. Connection errors, authentication failures,
non-5xx responses, an unavailable API, malformed/future cooldown state and
already recovered Web responses do not trigger a restart. No configuration,
plugin, image or library data is changed. This is not a general outage monitor.

Deployment: preserve the old executable and unit/drop-ins privately, install
the reviewed script at the existing executable path, add the environment-file
drop-in, reload systemd and run only a **healthy** one-shot check. Require the
`last_ok` timestamp to advance and the Jellyfin container's start time to remain
unchanged. The existing timer and logrotate policy must remain intact; do not
create a second timer. Rollback restores the previous script/drop-ins and
reloads systemd. Never force a real production500 solely to test recovery.

The audit found no previous rotation rule for this log. Install the supplied
`logrotate.conf` as `/etc/logrotate.d/jellyfin-web-watchdog`; validate the whole
logrotate configuration in debug mode before activation. Its daily/2MiB size
threshold, seven retained rotations and compression prevent endless retention.

Run `python3 -m unittest discover -s integration/server/web-watchdog` for the
hermetic fake-curl/Docker tests. Runtime deployment and deliberate failure
acceptance are separate from those source tests.
