"""Conservative, idempotent live-channel display names; never changes identities."""
import re
import json
from pathlib import Path

_review_file = Path(__file__).with_name('venom-reviewed-channel-names.json')
REVIEWED = json.loads(_review_file.read_text()) if _review_file.exists() else {}


def clean_name(value):
    original = str(value).strip()
    if original in REVIEWED:
        return REVIEWED[original]
    label = re.sub(r'^\d{3,6}\s+(?=(?:VIP\b|CA\b|UK\b|US\b|AR\b|NW\b))', '', original, flags=re.I)
    label = re.sub(r'^(?:(?:VIP|CA|UK|US|AR|NW)\b[\s:|.-]*)+', '', label, flags=re.I).strip()
    # Verified provider kids-category prefix, not part of the station name.
    label = re.sub(r'^(?:\d{1,6}\s+)?KD\s*:\s*', '', label, flags=re.I).strip()
    # Explicit provider markers seen in the expanded catalogue. Delimiters are
    # required so real station names such as US TV/ARTE remain intact.
    label=re.sub(r'^\s*(?:\d{1,6}\s+)?\[SPO\]\s*','',label,flags=re.I)
    label=re.sub(r'^(?:\d{1,6}\s+)?(?:(?:USA|US|UK|CA|AR|SP|DS|NW|KD|LB|SY|UAE)\s*[:|]\s*)+','',label,flags=re.I)
    label=re.sub(r'^LB\s*,\s*','',label,flags=re.I)
    label=re.sub(r'^(MBC|OSN)\s*:\s*',r'\1 ',label,flags=re.I)
    label=re.sub(r'\s+',' ',label).strip()
    return label or original


def previous_clean_name(value):
    original = str(value).strip()
    label = re.sub(r'^\d{3,6}\s+(?=(?:VIP\b|CA\b|UK\b|US\b|AR\b|NW\b))', '', original, flags=re.I)
    label = re.sub(r'^(?:(?:VIP|CA|UK|US|AR|NW)\b[\s:|.-]*)+', '', label, flags=re.I).strip()
    return label or original


def planned_override(source, current, previous):
    if current is not None and (not previous or current != previous['applied']):
        return current  # A user's explicit edit takes priority.
    desired=clean_name(source)
    return current if desired == source and current is None else desired
