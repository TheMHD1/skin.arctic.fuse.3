# Provider-presence corroboration

Deployed 2026-09-14 on media CT102 / Dispatcharr. This is read-only with respect
to provider data and channel visibility; it opens no playback streams.

- Script: `/data/config/dispatcharr/venom-provider-presence-audit.py` on the host,
  `/data/venom-provider-presence-audit.py` inside Dispatcharr.
- Database: `/data/config/dispatcharr/provider-presence.sqlite3` (0600).
- Timer: `venom-provider-presence.timer`, daily 05:30 UTC plus up to 15 minutes
  random delay; persistent missed-run recovery. First scheduled run 05:39 UTC.
- Service uses a nonblocking lock and a three-minute timeout.
- Reads the actual provider `get_live_streams` metadata using existing private
  credentials. Saves only source IDs, gateway IDs, presence state and timestamps.
  Response size, shape, count, and large-catalogue-shrink checks fail closed.
- Retains 30 days of observations. Any mapped fallback source still present
  counts the channel as present; missing mappings are unknown, not absence.
- First successful result: provider 11,249; mapped present 11,249; absent 0;
  unmapped 0. Systemd unit/timer verification passed.

**Not a dead-channel verdict.** Catalogue presence does not prove playback;
absence does not alone prove permanent failure. This supplies independent
multi-day corroboration to the conservative health policy. Playback timeouts,
capacity contention and temporary errors still do not trigger hiding. Automatic
hiding remains disabled pending integration of controlled permanent-failure
evidence and reversible recovery handling.
