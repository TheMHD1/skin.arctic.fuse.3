"""Refresh only Home widgets, without reloading the skin or interrupting video."""
import time
import xbmc
import xbmcgui

class Monitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.due = 0

    def onNotification(self, sender, method, data):
        if method in ('Player.OnStop', 'VideoLibrary.OnUpdate', 'VideoLibrary.OnScanFinished'):
            self.due = max(self.due, time.monotonic()+4)


class RefreshClock:
    """Strictly increasing cache-busters, independent of wall-clock changes."""
    def __init__(self):
        self.value = 0

    def next(self):
        self.value = max(self.value+1, time.monotonic_ns())
        return str(self.value)


def home_hub_active():
    return (xbmc.getCondVisibility('Window.IsActive(home)')
            or xbmc.getCondVisibility('Window.IsActive(videos)'))


def refresh_decision(active, entered, now, last, due):
    event_due = bool(due and now >= due)
    return (active and ((not entered and now-last > 5)
                        or now-last >= 60 or event_due), event_due)

def main():
    monitor = Monitor()
    refresh_clock = RefreshClock()
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
        home_hub = home_hub_active()
        active = (xbmc.getSkinDir() == 'skin.arctic.fuse.3'
                  and home_hub
                  and not xbmc.getCondVisibility('Player.HasMedia')
                  and not xbmc.getCondVisibility('System.HasModalDialog'))
        now = time.monotonic()
        discover = (xbmc.getSkinDir() == 'skin.arctic.fuse.3'
                    and xbmc.getCondVisibility('Window.IsActive(1101)')
                    and not xbmc.getCondVisibility('Player.HasMedia')
                    and not xbmc.getCondVisibility('System.HasModalDialog'))
        if discover and ((not discover_entered and now-discover_last>5) or now-discover_last>=60):
            home.setProperty('Habibi.Discover.Refresh',refresh_clock.next())
            discover_last=now
        discover_entered=discover
        refresh, event_due = refresh_decision(active, entered, now, last, monitor.due)
        if refresh:
            home.setProperty('Habibi.Home.Refresh', refresh_clock.next())
            last = now
            # An entry/periodic refresh before the four-second event grace must
            # not consume the later refresh that sees the committed server state.
            if event_due:
                monitor.due = 0
        entered = active
    home.clearProperty('Habibi.Home.Refresh')
    home.clearProperty('Habibi.Home.ServiceAlive')

if __name__ == '__main__':
    main()
