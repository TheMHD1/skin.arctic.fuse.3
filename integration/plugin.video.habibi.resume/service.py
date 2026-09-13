"""Refresh only Home widgets, without reloading the skin or interrupting video."""
import time
import xbmc
import xbmcgui

class Monitor(xbmc.Monitor):
    due = 0
    def onNotification(self, sender, method, data):
        if method in ('Player.OnStop', 'VideoLibrary.OnUpdate', 'VideoLibrary.OnScanFinished'):
            self.due = time.monotonic()+4

def main():
    monitor = Monitor()
    home = xbmcgui.Window(10000)
    # Avoid duplicate launch if a manual start overlaps Kodi's service startup.
    try:
        if time.time()-float(home.getProperty('Habibi.Home.ServiceAlive') or 0)<10:
            return
    except ValueError:
        pass
    home.setProperty('Habibi.Home.ServiceAlive', str(time.time()))
    xbmc.log('Habibi Home: refresh service started', xbmc.LOGINFO)
    try:
        from integrity import startup_check
        startup_check()
    except Exception as error:
        xbmc.log('Habibi compatibility check unavailable: '+type(error).__name__,xbmc.LOGWARNING)
    last = 0
    discover_last = 0
    discover_entered = False
    entered = False
    while not monitor.waitForAbort(1):
        home.setProperty('Habibi.Home.ServiceAlive', str(time.time()))
        active = (xbmc.getSkinDir() == 'skin.arctic.fuse.3'
                  and xbmc.getCondVisibility('Window.IsActive(home)')
                  and not xbmc.getCondVisibility('Player.HasMedia')
                  and not xbmc.getCondVisibility('System.HasModalDialog'))
        now = time.monotonic()
        discover = (xbmc.getSkinDir() == 'skin.arctic.fuse.3'
                    and xbmc.getCondVisibility('Window.IsActive(1101)')
                    and not xbmc.getCondVisibility('Player.HasMedia')
                    and not xbmc.getCondVisibility('System.HasModalDialog'))
        if discover and ((not discover_entered and now-discover_last>5) or now-discover_last>=60):
            home.setProperty('Habibi.Discover.Refresh',str(time.time_ns()))
            discover_last=now
        discover_entered=discover
        if active and ((not entered and now-last > 5) or now-last >= 60 or (monitor.due and now >= monitor.due)):
            home.setProperty('Habibi.Home.Refresh', str(time.time_ns()))
            last = now
            monitor.due = 0
        entered = active
    home.clearProperty('Habibi.Home.Refresh')
    home.clearProperty('Habibi.Home.ServiceAlive')

if __name__ == '__main__':
    main()
