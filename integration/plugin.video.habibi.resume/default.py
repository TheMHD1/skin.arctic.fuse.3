"""Server-authoritative combined resume list; never changes watched state."""
import json
import sys
import time
from urllib.parse import urlencode, parse_qsl
from urllib.request import Request, urlopen
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
from client import Client, LABELS, play_path, valid_id
from titles import display_title, display_label

SEARCH_MODES = {
    'searchmovies': ('Movie', 'movies'),
    'searchshows': ('Series', 'shows'),
    'searchvenommovies': ('Movie', 'venom_movies'),
    'searchvenomshows': ('Series', 'venom_shows'),
}


def main():
    handle = int(sys.argv[1])
    try:
        auth_path = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.jellyfin/data.json')
        with open(auth_path, encoding='utf-8') as stream:
            server = json.load(stream)['Servers'][0]
        base = server['address'].rstrip('/')
        token = server['AccessToken']
        params = dict(parse_qsl(sys.argv[2].lstrip('?')))
        mode = params.get('mode', 'resume')
        scope_path=xbmcvfs.translatePath('special://profile/addon_data/plugin.video.habibi.resume/home-library-scopes.json')
        try:
            with open(scope_path,encoding='utf-8') as stream:scopes=json.load(stream)
        except FileNotFoundError:scopes={}
        client = Client(server,scopes)
        if mode == 'setfavorite':
            enabled = params.get('value') == 'true'
            client.set_favorite(valid_id(params.get('id')), enabled)
            xbmcgui.Window(10000).setProperty('Habibi.Home.Refresh', str(time.time_ns()))
            xbmcgui.Window(10000).clearProperty('Habibi.Discover.LibraryIndex')
            xbmcgui.Window(10000).setProperty('Habibi.Discover.Refresh', str(time.time_ns()))
            xbmcgui.Dialog().notification('Jellyfin', 'Added to Favorites' if enabled else 'Removed from Favorites')
            if xbmc.getCondVisibility('Window.IsActive(videos)'):
                xbmc.executebuiltin('Container.Refresh')
            return
        if mode == 'following':
            item = client.following(valid_id(params.get('id')))
            if item:
                xbmc.executebuiltin('PlayMedia('+play_path(item['Id'],server['Id'])+')')
            else:
                xbmcgui.Dialog().notification('Jellyfin', 'No following episode is available')
            return
        start = max(0,int(params.get('start',0)))
        listing_started = time.monotonic()
        is_search = mode in SEARCH_MODES
        query = params.get('query', '')
        if is_search:
            from search import search
            kind, scope = SEARCH_MODES[mode]
            items = search(client, query, kind, start, scope=scope)
        else:
            items = client.listing(mode, params.get('series'), start)
        rows = []
        for item in items:
            kind = item.get('Type')
            if kind not in ('Movie', 'Episode', 'Series'):
                continue
            path = ('plugin://plugin.video.habibi.resume/?'+urlencode({'mode':'series','series':valid_id(item['Id'])})) if kind == 'Series' else play_path(item['Id'],server['Id'])
            label = display_label(item)
            li = xbmcgui.ListItem(label=label, path=path, offscreen=True)
            info = li.getVideoInfoTag()
            info.setTitle(display_title(item))
            provider_ids={k.lower():str(v) for k,v in item.get('ProviderIds',{}).items() if v}
            if provider_ids:info.setUniqueIDs(provider_ids)
            if kind in ('Movie','Series') and provider_ids.get('imdb') and xbmc.getCondVisibility('System.HasAddon(slyguy.trailers)'):
                info.setTrailer('plugin://slyguy.trailers/?'+urlencode({'_':'/imdb','video_id':provider_ids['imdb']}))
            info.setMediaType('tvshow' if kind == 'Series' else kind.lower())
            info.setPlot(item.get('Overview', ''))
            info.setYear(item.get('ProductionYear', 0))
            if kind == 'Episode':
                info.setTvShowTitle(item.get('SeriesName', ''))
                info.setSeason(item.get('ParentIndexNumber', 0))
                info.setEpisode(item.get('IndexNumber', 0))
            user = item.get('UserData', {})
            info.setResumePoint(user.get('PlaybackPositionTicks', 0) / 10000000, item.get('RunTimeTicks', 0) / 10000000)
            info.setPlaycount(user.get('PlayCount', 0))
            li.setProperty('IsPlayable', 'false' if kind == 'Series' else 'true')
            li.setProperty('jellyfinid', item['Id'])
            li.setProperty('jellyfinserver', '')
            context = []
            if kind in ('Movie','Series') and xbmc.getCondVisibility('System.HasAddon(slyguy.trailers)'):
                trailer_action = ('PlayMedia(plugin://slyguy.trailers/?'+urlencode({'_':'/imdb','video_id':provider_ids['imdb']})+')') if provider_ids.get('imdb') else 'RunScript(slyguy.trailers)'
                context.append(('Watch trailer',trailer_action))
            if mode != 'series' and not is_search:
                context.append(('View all — '+LABELS[mode], 'ActivateWindow(Videos,plugin://plugin.video.habibi.resume/?mode='+mode+',return)'))
            favorite = bool(user.get('IsFavorite'))
            favorite_path = 'plugin://plugin.video.habibi.resume/?'+urlencode({'mode':'setfavorite','id':item['Id'],'value':'false' if favorite else 'true'})
            context.append(('Remove from Jellyfin Favorites' if favorite else 'Add to Jellyfin Favorites', 'RunPlugin('+favorite_path+')'))
            if kind == 'Episode' and item.get('SeriesId'):
                series_path = 'plugin://plugin.video.habibi.resume/?'+urlencode({'mode':'series','series':valid_id(item['SeriesId'])})
                following_path = 'plugin://plugin.video.habibi.resume/?'+urlencode({'mode':'following','id':valid_id(item['Id'])})
                context += [('Browse episodes', 'ActivateWindow(Videos,'+series_path+',return)'),
                            ('Play following episode', 'RunPlugin('+following_path+')')]
            if kind != 'Series':
                action = 'unwatched' if user.get('Played') else 'watched'
                action_path = 'plugin://plugin.video.jellyfin/?'+urlencode({'mode':action,'id':item['Id']})
                context.append(('Mark as '+action, 'RunPlugin('+action_path+')'))
            li.addContextMenuItems(context)
            def artwork(item_id, image_type):
                return base + '/Items/' + item_id + '/Images/' + image_type + '?' + urlencode({'api_key': token, 'maxWidth': 1280, 'quality': 90})
            art = {'icon':'DefaultTVShows.png' if kind == 'Series' else 'DefaultVideo.png'}
            if item.get('ImageTags', {}).get('Primary'):
                art['thumb'] = artwork(item['Id'], 'Primary')
                art['poster'] = art['thumb']
            if kind == 'Episode' and item.get('SeriesId') and item.get('SeriesPrimaryImageTag'):
                art['poster'] = artwork(item['SeriesId'], 'Primary')
            if item.get('BackdropImageTags'):
                art['fanart'] = artwork(item['Id'], 'Backdrop/0')
            elif item.get('ParentBackdropItemId') and item.get('ParentBackdropImageTags'):
                art['fanart'] = artwork(item['ParentBackdropItemId'], 'Backdrop/0')
            li.setArt(art)
            rows.append((path, li, kind == 'Series'))
        page_size = 100 if mode == 'series' else 30
        if len(items) == page_size:
            more_params = {'mode':mode,'start':start+page_size}
            if is_search:more_params['query']=query
            if mode == 'series':more_params['series']=valid_id(params.get('series'))
            path = 'plugin://plugin.video.habibi.resume/?'+urlencode(more_params)
            more = xbmcgui.ListItem(label='More…',path=path,offscreen=True)
            rows.append((path,more,True))
        xbmcplugin.setContent(handle, 'episodes' if mode == 'series' else 'videos')
        xbmcplugin.setPluginCategory(handle, LABELS[mode]+' — Jellyfin')
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
        xbmc.log('Habibi Home: {} loaded {} cards in {:.3f}s'.format(mode,len(rows),time.monotonic()-listing_started), xbmc.LOGINFO)
    except Exception as error:
        # Never log credential-bearing URLs or exception strings.
        xbmc.log('Habibi Resume: list failed ({})'.format(type(error).__name__), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


if __name__ == '__main__':
    main()
