"""Preserve explicit Home intent across Python-window teardown."""
import hashlib
BROWSER='addons/plugin.video.venom.tv/browser.py'
HUB='addons/skin.arctic.fuse.3/1080i/Custom_1107_LiveTV.xml'
HUB_BEFORE='19adc46b3c7c994eda9d14a8f76f4b87fee8267ef860369f504540e4d71e9a84'
HUB_ACTION='RunScript(special://home/addons/plugin.video.venom.tv/browser.py,live)'
HUB_CONDITION='Skin.String(HomeSwitcher.1107.Name,Venom TV) + System.HasAddon(plugin.video.venom.tv)'
BEFORE={'local':'832606869ece94df80c01bcd1b0b3d4d66147d74c92b5e9ae36c91501caf162c',
        'remote':'b56bd320e64dfc1866db3995059ad8385259a6b6db8606e6bc968e168d28cd88'}
def replace(source,old,new):
    if source.count(old)!=1:raise ValueError('Unreviewed lifecycle anchor')
    return source.replace(old,new)
def hub(data):
    if hashlib.sha256(data).hexdigest()!=HUB_BEFORE:raise ValueError('Unreviewed Venom hub source')
    anchor='<onload condition="'+HUB_CONDITION+'">'+HUB_ACTION+'</onload>'
    # Evaluate before RunScript is queued, not inside a later script that may
    # run after the old browser has released its singleton during Back.
    condition=HUB_CONDITION+' + String.IsEmpty(Window(Home).Property(Venom.Browser.Open))'
    source=replace(data.decode(),anchor,'<onload condition="'+condition+'">'+HUB_ACTION+'</onload>')
    import xml.etree.ElementTree as ET
    ET.fromstring(source)
    return source.encode()
def transform(data,cohort):
    if hashlib.sha256(data).hexdigest()!=BEFORE[cohort]:raise ValueError('Unreviewed lifecycle source')
    source=data.decode()
    source=replace(source,"                and not xbmc.getCondVisibility('Player.HasMedia')\n",'')
    source=replace(source,'        super().close()\n',
        "        # Native close navigates to the previous window. After Home has\n        # already deactivated us, calling it would resurrect old history.\n        if not xbmc.getCondVisibility('Window.IsActive(home)'):super().close()\n")
    source=replace(source,'        # Native PVR fullscreen and temporary modal dialogs retain their window.',
        '        # Fullscreen and temporary modal dialogs retain their window.\n        # Explicit Home also retires a browser over background video without\n        # stopping that player. Cleanup must not override later navigation.')
    compile(source,'venom-lifecycle','exec');return source.encode()
