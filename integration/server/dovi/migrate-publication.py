#!/usr/bin/env python3
"""One-time copy of legacy notification intent; run with legacy writers stopped."""
import argparse
import importlib.util
from pathlib import Path
import sqlite3
import sys
import time


def migrate(source, destination):
    spec = importlib.util.spec_from_file_location('reconciler', Path(__file__).with_name('dovi-library-view-20260922.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with sqlite3.connect('file:' + str(source.resolve()) + '?mode=ro', uri=True) as old, module.connect(destination) as new:
        if new.execute("SELECT 1 FROM notification_meta WHERE key='legacy-migrated'").fetchone():
            return 0
        tables = {row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        count = 0
        if 'notification_outbox' in tables:
            for folder, in old.execute('SELECT folder FROM notification_outbox'):
                if module.publication_folder(Path(folder), Path('/data/media')) is None:
                    raise ValueError('unsafe legacy scope; investigate before migration')
                new.execute('INSERT OR IGNORE INTO notification_outbox(folder,first_seen) VALUES(?,?)', (folder, time.time()))
                count += 1
        if 'notification_receipts' in tables:
            for folder, sent_at in old.execute('SELECT folder,sent_at FROM notification_receipts'):
                new.execute('INSERT OR IGNORE INTO notification_receipts VALUES(?,?)', (folder, sent_at))
        new.execute("INSERT INTO notification_meta VALUES('legacy-migrated',?)", (str(time.time()),))
        new.commit()
        return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve():
        raise ValueError('migration requires separate databases')
    print({'copied_intents': migrate(args.source, args.destination)})
