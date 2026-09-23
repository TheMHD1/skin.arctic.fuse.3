"""Regenerate bounded search widgets while preserving reviewed stable GUIDs."""
import json
import xml.etree.ElementTree as ET

SECTIONS = ('skinvariables-searchwidgets-combined',
            'skinvariables-searchwidgets-wall',
            'skinvariables-searchwidgets-standard',
            'skinvariables-searchwidgets-selector',
            'skinvariables-searchwidgets-wall-selector',
            'skinvariables-searchwidgets-info')
ROWS = (
    ('502', 'Movies', 'film.png', 'searchmovies'),
    ('503', 'Shows', 'tv.png', 'searchshows'),
    ('504', 'Venom Movies — Not HD', 'film.png', 'searchvenommovies'),
    ('505', 'Venom Shows — Not HD', 'tv.png', 'searchvenomshows'),
)


def _param(node, name):
    result = node.find("param[@name='"+name+"']")
    if result is None:
        raise RuntimeError('Generated search node lacks '+name)
    return result


def _route(mode):
    return ('$VAR[Path_SearchTerm_SingleEncoded,'
            'plugin://plugin.video.habibi.resume/?mode='+mode+'&query=,]')


def transform(data):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(data, parser=parser)
    found = {node.get('name'):node for node in root.findall('include')
             if node.get('name') in SECTIONS}
    if set(found) != set(SECTIONS):
        raise RuntimeError('Generated search includes are missing or duplicated')

    for section in ('skinvariables-searchwidgets-combined',
                    'skinvariables-searchwidgets-wall'):
        children = list(found[section])
        if len(children) != 6:
            raise RuntimeError('Unreviewed generated search row count')
        for child, (item_id, _label, _icon, mode) in zip(children[:4], ROWS):
            _param(child, 'id').text = item_id
            _param(child, 'content').text = _route(mode)
            _param(child, 'include').text = 'List_Poster_Row'
            _param(child, 'target').text = 'videos'
        for child in children[4:]:
            found[section].remove(child)

    standard = found['skinvariables-searchwidgets-standard']
    group = standard.find("include[@content='Hub_Widgets_Grouplist']")
    children = list(group) if group is not None else []
    if len(children) != 6:
        raise RuntimeError('Unreviewed generated standard search row count')
    for child, (item_id, label, _icon, mode) in zip(children[:4], ROWS):
        _param(child, 'id').text = item_id
        _param(child, 'groupid').text = str(200+int(item_id))
        _param(child, 'label').text = label
        _param(child, 'include').text = 'List_Poster_Row'
        content = child.find('content')
        if content is None:
            raise RuntimeError('Generated standard search content is missing')
        content.set('target', 'videos')
        content.text = _route(mode)
    for child in children[4:]:
        group.remove(child)

    for section in ('skinvariables-searchwidgets-selector',
                    'skinvariables-searchwidgets-wall-selector'):
        children = list(found[section])
        if len(children) != 6:
            raise RuntimeError('Unreviewed generated search selector count')
        for child, (item_id, label, icon, _mode) in zip(children[:4], ROWS):
            label_node = child.find('label')
            icon_node = child.find('icon')
            widget_id = child.find("property[@name='widget_id']")
            if label_node is None or icon_node is None or widget_id is None:
                raise RuntimeError('Generated search selector is incomplete')
            label_node.text = label+'$INFO[Container('+item_id+').NumItems, (,)]'
            icon_node.text = 'special://skin/extras/icons/'+icon
            widget_id.text = '$NUMBER['+item_id+']'
        for child in children[4:]:
            found[section].remove(child)

    info = found['skinvariables-searchwidgets-info']
    children = list(info)
    if len(children) != 6:
        raise RuntimeError('Unreviewed generated search info count')
    for child, (item_id, _label, _icon, _mode) in zip(children[:4], ROWS):
        _param(child, 'id').text = item_id
    for child in children[4:]:
        info.remove(child)

    ET.indent(root, space='    ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)+b'\n'


def transform_nodes(data):
    rows = json.loads(data)
    if not isinstance(rows, list) or len(rows) != 6:
        raise RuntimeError('Unreviewed search widget node count')
    result = []
    for old, (_item_id, label, icon, mode) in zip(rows[:4], ROWS):
        if not isinstance(old, dict) or not str(old.get('guid','')).startswith('guid-'):
            raise RuntimeError('Search widget stable GUID is missing')
        row = dict(old)
        row.update(label=label, icon='special://skin/extras/icons/'+icon,
                   path={'searchmovies':'DefaultSearch-Movies',
                         'searchshows':'DefaultSearch-TvShows',
                         'searchvenommovies':'DefaultSearch-VenomMovies',
                         'searchvenomshows':'DefaultSearch-VenomShows'}[mode],
                   target='videos', widget_style='Poster')
        result.append(row)
    return (json.dumps(result, indent=4, ensure_ascii=False)+'\n').encode()
