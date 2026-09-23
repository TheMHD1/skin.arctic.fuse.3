"""Exact transformations for the Arctic 3.3.1 search/rating overlay."""
from copy import deepcopy
import xml.etree.ElementTree as ET


def _replace_once(data, old, new, name):
    if data.count(old) != 1:
        raise RuntimeError('Unreviewed '+name+' source')
    return data.replace(old, new)


def transform_search(data):
    data = _replace_once(
        data,
        b'<include name="Search_Switcher_Items">\n        <item>',
        b'<include name="Search_Switcher_Items">\n        <include>skinvariables-searchwidgets-selector-owned</include>\n        <item>',
        'search switcher')
    data = _replace_once(
        data, b'<include>skinvariables-searchwidgets-selector</include>',
        b'<include>skinvariables-searchwidgets-selector-venom</include>',
        'search selector')
    data = _replace_once(
        data,
        b'<include name="Search_Switcher_Wall_Items">\n        <item>',
        b'<include name="Search_Switcher_Wall_Items">\n        <include>skinvariables-searchwidgets-wall-selector-owned</include>\n        <item>',
        'wall search switcher')
    return _replace_once(
        data, b'<include>skinvariables-searchwidgets-wall-selector</include>',
        b'<include>skinvariables-searchwidgets-wall-selector-venom</include>',
        'wall search selector')


def transform_generated(data):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(data, parser=parser)
    for original, owned, venom in (
        ('skinvariables-searchwidgets-selector',
         'skinvariables-searchwidgets-selector-owned',
         'skinvariables-searchwidgets-selector-venom'),
        ('skinvariables-searchwidgets-wall-selector',
         'skinvariables-searchwidgets-wall-selector-owned',
         'skinvariables-searchwidgets-wall-selector-venom')):
        matches = [node for node in root.findall('include') if node.get('name') == original]
        if len(matches) != 1:
            raise RuntimeError('Unreviewed generated selector: '+original)
        source = matches[0]
        children = list(source)
        ids = [node.findtext("property[@name='widget_id']") for node in children]
        if ids != ['$NUMBER[502]','$NUMBER[503]','$NUMBER[504]','$NUMBER[505]']:
            raise RuntimeError('Unreviewed generated selector IDs')
        provider = deepcopy(source)
        source.set('name', owned)
        provider.set('name', venom)
        for child in list(source)[2:]:
            source.remove(child)
        for child in list(provider)[:2]:
            provider.remove(child)
        index = list(root).index(source)
        root.insert(index+1, provider)
    ET.indent(root, space='    ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)+b'\n'


RATING_VARIABLE = '''\n    <!-- A named rating is only labelled when its provenance is explicit. The\n         plain rating fallback deliberately remains provider-neutral. -->\n    <variable name="Label_Poster_Rating">\n        <value condition="!String.IsEmpty(ListItem.Property(Habibi.Rating.IMDb))">$INFO[ListItem.Property(Habibi.Rating.IMDb),IMDb ]</value>\n        <value condition="!String.IsEmpty(ListItem.Rating(imdb))">$INFO[ListItem.Rating(imdb),IMDb ]</value>\n        <value condition="!String.IsEmpty(ListItem.Rating(tmdb))">$INFO[ListItem.Rating(tmdb),TMDb ]</value>\n        <value condition="!String.IsEmpty(ListItem.Property(tmdb_id)) + !String.IsEmpty(ListItem.Rating)">$INFO[ListItem.Rating,TMDb ]</value>\n        <value condition="!String.IsEmpty(ListItem.Property(Habibi.Rating.Community))">$INFO[ListItem.Property(Habibi.Rating.Community),★ ]</value>\n        <value condition="!String.IsEmpty(ListItem.Rating)">$INFO[ListItem.Rating,★ ]</value>\n    </variable>\n'''.encode()


def transform_labels(data):
    anchor = b'''    <variable name="Label_MediaList_Details_LeftLabel">'''
    return _replace_once(data, anchor, RATING_VARIABLE+b'\n'+anchor, 'rating labels')


RATING_OBJECT = b'''    <include name="Object_PosterRating">\n        <definition>\n            <control type="group">\n                <right>12</right>\n                <bottom>12</bottom>\n                <width>132</width>\n                <height>40</height>\n                <visible>[String.IsEqual(ListItem.DBType,movie) | String.IsEqual(ListItem.DBType,tvshow)] + !String.IsEmpty($VAR[Label_Poster_Rating])</visible>\n                <control type="image">\n                    <texture border="18" colordiffuse="e6333333">common/box.png</texture>\n                </control>\n                <control type="label">\n                    <font>font_hint_bold</font>\n                    <align>center</align>\n                    <aligny>center</aligny>\n                    <textcolor>panel_fg_100</textcolor>\n                    <label>$VAR[Label_Poster_Rating]</label>\n                </control>\n            </control>\n        </definition>\n    </include>\n\n'''


def transform_objects(data):
    data = _replace_once(data, b'    <include name="Object_AlphabetLetter_Label">',
                         RATING_OBJECT+b'    <include name="Object_AlphabetLetter_Label">',
                         'poster rating object')
    return _replace_once(
        data,
        b'''                <nested />\n                <centerbottom>0</centerbottom>\n                <right>25</right>''',
        b'''                <nested />\n                <include content="Object_CenterBottom" condition="!$PARAM[poster_rating]"><param name="centerbottom">0</param></include>\n                <include content="Object_Bottom" condition="$PARAM[poster_rating]"><param name="bottom">52</param></include>\n                <right>25</right>''',
        'poster indicator position')


def transform_layouts(data):
    data = _replace_once(
        data,
        b'''                    <include condition="!$PARAM[selected] + $PARAM[indicator]" content="Object_Indicator">\n                        <param name="affix">$PARAM[affix]</param>\n                        <param name="listitem">$PARAM[listitem]</param>\n                    </include>''',
        b'''                    <include condition="!$PARAM[selected] + $PARAM[indicator]" content="Object_Indicator">\n                        <param name="affix">$PARAM[affix]</param>\n                        <param name="listitem">$PARAM[listitem]</param>\n                        <param name="poster_rating">!String.IsEmpty($VAR[Label_Poster_Rating])</param>\n                    </include>''',
        'poster indicator call')
    return _replace_once(
        data,
        b'''                        <param name="focusbounce">true</param>\n                    </include>\n                </control>\n\n            </control>\n\n        </definition>\n    </include>\n\n    <include name="Layout_Reviews">''',
        b'''                        <param name="focusbounce">true</param>\n                    </include>\n                    <include content="Object_PosterRating" />\n                </control>\n\n            </control>\n\n        </definition>\n    </include>\n\n    <include name="Layout_Reviews">''',
        'poster rating call')
