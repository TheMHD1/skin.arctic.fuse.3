"""Conservative, idempotent live-channel display names; never changes identities."""
import re


def clean_name(value):
    original = str(value).strip()
    label = re.sub(r'^\d{3,6}\s+(?=(?:VIP\b|CA\b|UK\b|US\b|AR\b|NW\b))', '', original, flags=re.I)
    label = re.sub(r'^(?:(?:VIP|CA|UK|US|AR|NW)\b[\s:|.-]*)+', '', label, flags=re.I).strip()
    return label or original


def planned_override(source, current, previous):
    if current is not None and (not previous or current != previous['applied']):
        return current  # A user's explicit edit takes priority.
    desired=clean_name(source)
    return current if desired == source and current is None else desired
