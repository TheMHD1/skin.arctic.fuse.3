"""Derive local repairs from the SAME generic functions used by the remote build."""
import hashlib
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


ui = module('shared_ui', HERE.parent/'ui-reliability/overlay.py')
focus = module('shared_focus', HERE.parent/'remote-catchup/overlay.py')
BEFORE = dict(ui.BEFORE)
BEFORE['addons/plugin.video.venom.tv/browser.py'] = 'f8d1c57b08a03e3df73036c91e760214e4127ee6a697c6e83ee6f15af558b281'
BEFORE['addons/skin.arctic.fuse.3/1080i/Includes_Objects.xml'] = '15d224e74f8fbcba188f25051ef5922581b09e79ff263cd8ebbbc2b727e44fd2'


def transform(name, data):
    if hashlib.sha256(data).hexdigest() != BEFORE[name]:
        raise ValueError('Unreviewed local source: '+name)
    source = data.decode()
    if name.endswith('/browser.py'):
        source = focus.browser(ui.browser(source, remote=False), remote=False)
    elif name.endswith('/jellyfin_bridge.py'):
        source = ui.bridge(source)
    else:
        source = ui.replace(source, '!String.IsEmpty($VAR[Label_Poster_Rating])', ui.RATING)
        if name.endswith('/Includes_Objects.xml'):
            source = ui.replace(source, '<include name="Object_Indicator">\n',
                                '<include name="Object_Indicator">\n        <param name="poster_rating">false</param>\n')
    if name.endswith('.py'):
        compile(source, name, 'exec')
    else:
        ET.fromstring(source)
    return source.encode()
