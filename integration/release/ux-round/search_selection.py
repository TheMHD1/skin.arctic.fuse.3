"""Select owned results once per query with queued GUI actions, never network."""
import xbmc

class SearchSelection:
    def __init__(self):
        self.query=None;self.pending=False;self.changed=0

    def observe(self,active,query,now,updating=False,manual=False):
        if not active:
            self.pending=False
            return False
        if query!=self.query:
            self.query=query;self.changed=now;self.pending=bool(query.strip())
        if not self.pending:return False
        # A deliberate section choice wins; never force it back every second.
        if manual or now-self.changed>30:
            self.pending=False
            return False
        if updating or now-self.changed<1:return False
        self.pending=False
        return True

    def poll(self,now):
        active=(xbmc.getSkinDir()=='skin.arctic.fuse.3'
                and xbmc.getCondVisibility('Window.IsActive(1105)')
                and xbmc.getInfoLabel('Skin.String(HomeSwitcher.Search.Mode)')=='Combined'
                and xbmc.getInfoLabel('Container(3003).ListItem.Property(mode)')=='search')
        if not active:
            self.observe(False,'',now)
            return
        # Virtual keyboard has not committed yet; wait without consuming the query.
        if xbmc.getCondVisibility('System.HasActiveModalDialog'):return
        query=xbmc.getInfoLabel('Control.GetLabel(3000).index(1)')
        updating=any(xbmc.getCondVisibility('Container(%d).IsUpdating'%cid) for cid in (502,503))
        # The selector can already contain cached/provider rows before owned
        # widgets finish their request. Do not consume the one-shot on those
        # rows. A miss retains the skin's fallback; a later owned hit wins.
        counts=[xbmc.getInfoLabel('Container(%d).NumItems'%cid) for cid in (502,503)]
        updating=updating or not any(v.isdigit() and int(v)>0 for v in counts)
        # Navigation away from editing consumes the pending reset as a user
        # choice, including a section selected before its request completes.
        manual=not xbmc.getCondVisibility('Control.HasFocus(3000)')
        if not self.observe(True,query,now,updating,manual):return
        # Selector order is already owned Movies/Shows → other sources.
        count=xbmc.getInfoLabel('Container(601).NumItems')
        if not count.isdigit() or int(count)==0:return
        # This selector is hidden and SetFocus does not reliably select it.
        # Move through the supported GUI message path, without native Python
        # Control mutation or moving the user's keyboard focus. CurrentItem is
        # one-based; the ordered first available row is the owned section.
        position=xbmc.getInfoLabel('Container(601).CurrentItem')
        if position.isdigit() and 1<int(position)<=int(count):
            xbmc.executebuiltin('Control.Move(601,%d)'%(1-int(position)))
