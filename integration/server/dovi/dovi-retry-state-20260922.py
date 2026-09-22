#!/usr/bin/env python3
"""Persistent per-source conversion cooldown; caller holds converter flock.

Exit 75 means deferred. A changed source starts a fresh attempt budget.
No media content is read or modified. Database failures fail closed.
"""
import argparse
import sqlite3
import time
from pathlib import Path

COOLDOWN = 24 * 3600

def fingerprint(path):
    st = path.stat()
    return f'{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}'

def check(db, source, action, now=None, expected=None):
    now = time.time() if now is None else now
    source = Path(source)
    signature = fingerprint(source)
    if expected is not None and signature != expected:
        return 76  # Source changed since admission; do not charge its replacement.
    with sqlite3.connect(db, timeout=10) as con:
        con.execute('CREATE TABLE IF NOT EXISTS retries '
                    '(path TEXT PRIMARY KEY, signature TEXT NOT NULL, '
                    'attempts INTEGER NOT NULL, available REAL NOT NULL)')
        row = con.execute('SELECT signature, attempts, available FROM retries WHERE path=?',
                          (str(source),)).fetchone()
        attempts, available = (row[1], row[2]) if row and row[0] == signature else (0, 0)
        if action == 'clear':
            con.execute('DELETE FROM retries WHERE path=?', (str(source),))
            return 0
        if action == 'check':
            return 75 if available > now else 0
        if action != 'failure':
            raise ValueError('unsupported action')
        # After a cooldown expires, allow a new pair of attempts.
        if available and available <= now:
            attempts = 0
        attempts += 1
        available = now + COOLDOWN if attempts >= 2 else 0
        con.execute('INSERT INTO retries VALUES (?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                    'signature=excluded.signature, attempts=excluded.attempts, available=excluded.available',
                    (str(source), signature, attempts, available))
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['snapshot', 'check', 'failure', 'clear'])
    parser.add_argument('source', type=Path)
    parser.add_argument('--db', type=Path, default=Path('/data/config/_dovi/retry-state.sqlite'))
    parser.add_argument('--signature')
    args = parser.parse_args()
    if args.action in ('failure', 'clear') and not args.signature:
        parser.error('mutation requires the admitted source signature')
    signature = fingerprint(args.source) if args.action == 'snapshot' else args.signature
    result = check(args.db, args.source, 'check' if args.action == 'snapshot' else args.action,
                   expected=signature)
    if result == 0 and args.action == 'snapshot':
        print(signature)
    raise SystemExit(result)
