import xbmc
if xbmc.getCondVisibility('Player.HasMedia'):
    raise RuntimeError('Wait until idle')
xbmc.executebuiltin('RunScript(script.skinvariables,action=buildtemplate,force=true,no_reload=true)')
xbmc.log('Jellyfin library search: rebuilding templates; restart skin only after build completes.',xbmc.LOGINFO)
