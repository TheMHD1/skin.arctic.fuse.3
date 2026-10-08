"""Bound removed-item dispatch to the current item and Kodi database."""
import hashlib
SOURCE='addons/plugin.video.jellyfin/jellyfin_kodi/library.py'
BEFORE='ae141acb680eb375f41eecf76d467aa0d5f21fa7d30dd35e94a665d2b4a5e925'
def replace(source,old,new):
    if source.count(old)!=1:raise ValueError('Unreviewed removal anchor')
    return source.replace(old,new)
def transform(data):
    if hashlib.sha256(data).hexdigest()!=BEFORE:raise ValueError('Unreviewed removal source')
    source=data.decode();start=source.index('class RemovedWorker(');end=source.index('\nclass NotifyWorker(',start)
    worker=source[start:end]
    worker=replace(worker,'                musicvideos = MusicVideos(*default_args)\n',
        '                musicvideos = MusicVideos(*default_args)\n'
        '                removers = {"Movie": movies.remove, "BoxSet": movies.remove,\n'
        '                            "Series": tvshows.remove, "Season": tvshows.remove,\n'
        '                            "Episode": tvshows.remove, "MusicVideo": musicvideos.remove}\n')
    worker=replace(worker,'                music = Music(*default_args)\n',
        '                music = Music(*default_args)\n'
        '                removers = dict.fromkeys(("MusicAlbum", "MusicArtist", "AlbumArtist", "Audio"), music.remove)\n')
    begin=worker.index('                if item["Type"] == "Movie":\n');finish=worker.index('                except LibraryException as error:',begin)
    worker=worker[:begin]+('                try:\n'
        '                    obj = removers.get(item.get("Type"))\n'
        '                    if obj is None:\n'
        '                        LOG.warning("Skipping unsupported removal type %s in %s", item.get("Type"), kodidb.db_file)\n'
        '                    else:\n'
        '                        obj(item["Id"])\n')+worker[finish:]
    result=source[:start]+worker+source[end:]
    compile(result,'jellyfin-removal','exec');return result.encode()
