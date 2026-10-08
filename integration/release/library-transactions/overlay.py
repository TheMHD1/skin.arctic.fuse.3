"""Release completed sync writes before waits; preload collection network pages."""
import hashlib

LIBRARY = 'addons/plugin.video.jellyfin/jellyfin_kodi/library.py'
MOVIES = 'addons/plugin.video.jellyfin/jellyfin_kodi/objects/movies.py'
BEFORE = {LIBRARY: 'e58c7cb29e358feecf8a0c41838e08047c08860af9e9d7b62d3a1ff6257009eb',
          MOVIES: 'ff729912866fbbde9699df23c4398c535e7c89512a0db33a0e5cc3126620114d'}

def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Unreviewed transaction anchor')
    return source.replace(old, new)

def transform(name, data):
    if name not in BEFORE or hashlib.sha256(data).hexdigest() != BEFORE[name]:
        raise ValueError('Unreviewed transaction source')
    source = data.decode()
    if name == LIBRARY:
        for classname, following in (('UpdateWorker', 'UserDataWorker'),
                                     ('UserDataWorker', 'SortWorker'),
                                     ('RemovedWorker', 'NotifyWorker')):
            start = source.index('class ' + classname + '(')
            end = source.index('\nclass ' + following + '(', start)
            worker = source[start:end]
            if classname == 'UpdateWorker':
                worker = replace(worker, '                        self.queue.task_done()\n                        continue\n',
                                 '                        continue\n')
            if classname == 'RemovedWorker':
                old = '                finally:\n                    self.queue.task_done()\n'
            else:
                old = '\n                self.queue.task_done()\n'
            worker = replace(worker, old,
                '                finally:\n'
                '                    # Do not retain SQLite writes across queue/network/GUI waits.\n'
                '                    # Keep one item atomic and preserve existing error commits.\n'
                '                    try:\n'
                '                        kodidb.conn.commit()\n'
                '                        jellyfindb.conn.commit()\n'
                '                    finally:\n'
                '                        self.queue.task_done()\n')
            source = source[:start] + worker + source[end:]
    else:
        start = source.index('    def boxset(self, item, e_item):')
        end = source.index('\n    def boxsets_reset(', start)
        methods = source[start:end]
        methods = replace(methods, '        obj["Overview"] = API.get_overview(obj["Overview"])\n',
            '        obj["Overview"] = API.get_overview(obj["Overview"])\n'
            '        # Exhaust the network iterator before the first collection write.\n'
            '        # A slow/failed request must not block Kodi playback shutdown.\n'
            '        pages = tuple(server.get_movies_by_boxset(obj["Id"]))\n')
        methods = replace(methods, '        self.boxset_current(obj)\n', '        self.boxset_current(obj, pages)\n')
        methods = replace(methods, '    def boxset_current(self, obj):\n', '    def boxset_current(self, obj, pages):\n')
        methods = replace(methods, '        for all_movies in server.get_movies_by_boxset(obj["Id"]):\n',
                          '        for all_movies in pages:\n')
        source = source[:start] + methods + source[end:]
    compile(source, 'jellyfin-short-transactions', 'exec')
    return source.encode()
