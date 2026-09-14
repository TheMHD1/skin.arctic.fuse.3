"""Private, atomic user state. No provider credentials or playback URLs."""
import fcntl
import json
import os
import tempfile


def read(root):
    try:
        with open(os.path.join(root, 'library.json'), encoding='utf-8') as source:
            value = json.load(source)
    except FileNotFoundError:
        return {'favorites': {}, 'resume': {}}
    if not isinstance(value, dict):
        raise ValueError('Invalid Venom library state')
    return value


def update(root, callback):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, 'library.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = read(root)
        result = callback(value)
        descriptor, path = tempfile.mkstemp(prefix='.library-', suffix='.tmp', dir=root)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as target:
                json.dump(value, target, ensure_ascii=False)
                target.flush()
                os.fsync(target.fileno())
            os.replace(path, os.path.join(root, 'library.json'))
        finally:
            if os.path.exists(path):
                os.unlink(path)
        return result


def toggle_favorite(root, key, entry):
    def change(value):
        favorites = value.setdefault('favorites', {})
        if key in favorites:
            del favorites[key]
            return False
        favorites[key] = entry
        return True
    return update(root, change)
