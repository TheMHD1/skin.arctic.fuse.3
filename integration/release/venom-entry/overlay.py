"""Enable the explicit Venom Home route without a native-PVR dependency."""
import hashlib
import xml.etree.ElementTree as ET

SKIN='addons/skin.arctic.fuse.3/1080i/Includes_Home.xml'
BEFORE='a6572eb7429bd7b75c6164b7ab36c9f56cd8b0c415ae247da17cd29bdda04b9d'
OLD='!String.IsEmpty(Skin.String(HomeSwitcher.1107.Toggle)) + System.HasPVRAddon + PVR.HasTVChannels'
NEW='!String.IsEmpty(Skin.String(HomeSwitcher.1107.Toggle)) + [[Skin.String(HomeSwitcher.1107.Name,Venom TV) + System.HasAddon(plugin.video.venom.tv)] | [!Skin.String(HomeSwitcher.1107.Name,Venom TV) + System.HasPVRAddon + PVR.HasTVChannels]]'

def enabled(toggle,venom,addon,pvr,channels):
    """Truth table for the Kodi predicate; native PVR keeps its old guard."""
    return bool(toggle and ((venom and addon) or (not venom and pvr and channels)))

def transform(data):
    if hashlib.sha256(data).hexdigest()!=BEFORE:raise ValueError('Unreviewed Home source')
    source=data.decode()
    if source.count(OLD)!=1:raise ValueError('Unreviewed Home condition anchor')
    output=source.replace(OLD,NEW).encode()
    root=ET.fromstring(output)
    node=root.find("./include[@name='Home_ControlList_Item_1107']/include/param[@name='enabled']")
    if node is None or node.text!=NEW:raise ValueError('Wrong Home control modified')
    return output
