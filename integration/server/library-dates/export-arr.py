#!/usr/bin/env python3
"""Read-only export of installed Arr file-import dates. Output is PRIVATE."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3


def export(root):
    rows = []
    for app, filename, query in (
        ('radarr', 'radarr.db', 'SELECT m.Path,f.RelativePath,f.DateAdded FROM MovieFiles f JOIN Movies m ON m.Id=f.MovieId'),
        ('sonarr', 'sonarr.db', 'SELECT s.Path,f.RelativePath,f.DateAdded FROM EpisodeFiles f JOIN Series s ON s.Id=f.SeriesId'),
    ):
        with sqlite3.connect('file:' + str(root / app / filename) + '?mode=ro', uri=True, timeout=15) as db:
            for parent, relative, date in db.execute(query):
                path = Path(parent) / relative
                if not path.is_file() or not date:
                    continue
                imported = dt.datetime.fromisoformat(date.replace('Z', '+00:00'))
                if imported.tzinfo is None:
                    imported = imported.replace(tzinfo=dt.timezone.utc)
                rows.append({'path': str(path), 'realpath': str(path.resolve()),
                             'date': imported.astimezone(dt.timezone.utc).isoformat(), 'source': app})
    return {'schema': 1, 'files': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-root', type=Path, default=Path('/data/config'))
    print(json.dumps(export(parser.parse_args().config_root), indent=2))
