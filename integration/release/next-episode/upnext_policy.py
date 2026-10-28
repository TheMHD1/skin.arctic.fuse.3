"""Version-pinned, non-personal Up Next autoplay policy checks."""
import xml.etree.ElementTree as ET

UPNEXT_TAG = "v1.3.0"
UPNEXT_COMMIT = "a7cadd1b0f706c41335323da30f2079e09d4f3a9"

# These settings describe behavior, not an importable user profile.  They
# deliberately leave visual choices, language and account state unmanaged.
AUTOPLAY_POLICY = {
    "simpleMode": "1",
    "autoPlayMode": "0",       # automatic Play next
    "stopAfterClose": "false", # dismiss/Back leaves current episode playing
    "enablePlaylist": "false", # Jellyfin add-on remains transport owner
    "includeWatched": "true",  # a rewatch still progresses
    "playedInARow": "3",       # intentional Still Watching boundary
    "autoPlaySeasonTime": "120",
    "disableNextUp": "false",
}


def parse_settings(xml_bytes):
    root = ET.fromstring(xml_bytes)
    return {node.get("id"): (node.text or "").strip() for node in root.findall("setting")}


def validate_policy(xml_bytes):
    values = parse_settings(xml_bytes)
    errors = [name for name, expected in AUTOPLAY_POLICY.items() if values.get(name) != expected]
    if errors:
        raise ValueError("Up Next autoplay policy mismatch: " + ", ".join(errors))
    return True
