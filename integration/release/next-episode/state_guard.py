"""Pure state-safety contract for an authorized live playback probe.

The caller is responsible for collecting snapshots through authenticated local
APIs.  This module deliberately has no credentials, network calls, or writes.
"""
from datetime import datetime, timezone

USER_FIELDS = ("Played", "PlayCount", "PlaybackPositionTicks", "LastPlayedDate")
LOCAL_FIELDS = ("kodi_resume_field", "kodi_playcount")


def normalize_timestamp(value):
    """Canonicalize equivalent ISO-8601 UTC formatting without inventing time."""
    if value is None:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def normalize_user_data(user_data):
    return {
        "Played": user_data.get("Played"),
        "PlayCount": None if user_data.get("PlayCount") is None else int(user_data["PlayCount"]),
        "PlaybackPositionTicks": (None if user_data.get("PlaybackPositionTicks") is None
                                   else int(user_data["PlaybackPositionTicks"])),
        "LastPlayedDate": normalize_timestamp(user_data.get("LastPlayedDate")),
    }


def probe_eligible(before):
    """A nullable baseline cannot be faithfully restored by Jellyfin's DTO."""
    if before is None:
        return False
    return all(value is not None for value in normalize_user_data(before.get("server_user_data", {})).values())


def normalize(snapshot):
    """Keep only behaviorally relevant, serializable state fields."""
    server = snapshot.get("server_user_data", {})
    return {
        "server_user_data": normalize_user_data(server),
        **{field: snapshot.get(field) for field in LOCAL_FIELDS},
    }


def restoration_permitted(before, after_test, current):
    """Return true only if no actor changed state after the controlled test.

    `before` is intentionally part of the signature: callers cannot invoke a
    restore path without first proving that a baseline exists.
    """
    if not probe_eligible(before) or after_test is None or current is None:
        return False
    return normalize(after_test) == normalize(current)


def restoration_plan(before, after_test, current):
    """Return the original state only when restoration is safe; otherwise None."""
    return normalize(before) if restoration_permitted(before, after_test, current) else None
