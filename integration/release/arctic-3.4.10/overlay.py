"""Fail-closed semantic overlay for upstream Arctic Fuse 3 3.4.10.

This is source-only: it never reads a Kodi profile or talks to a device.  The
release builder supplies a clean checkout at UPSTREAM_COMMIT, transforms a
private temporary copy, and emits the reviewed changed-file payload and patch.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

UPSTREAM_COMMIT = "7206a2a1d2f9d62a025c495619a9e07d53dd2be7"
SKIN_VERSION = "3.4.10"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(data: bytes, old: bytes, new: bytes, purpose: str) -> bytes:
    if data.count(old) != 1:
        raise RuntimeError("unreviewed {} preimage".format(purpose))
    return data.replace(old, new)


COMBINED_OWNED = b'''<contents>
    <value name="comments">Habibi owned search selector (combined/wall)</value>
    <template>generator/data/parts/basic_include.xmltemplate</template>
    <value name="includes_name">skinvariables-searchwidgets-combined-selector-owned</value>
    <value name="includes_part">
        <items menu="searchwidgets">
            <item>
                <template>generator/data/parts/search_item_combined.xmltemplate</template>
                <condition>{item_path}!=</condition>
                <condition>{item_disabled}!=True</condition>
                <condition>{item_path}==DefaultSearch-Movies||{item_path}==DefaultSearch-TvShows</condition>
                <value name="hide_overlay">true</value>
                <value name="widget_id">$MATH[500 + {item_x} + 2]</value>
            </item>
        </items>
    </value>
</contents>
'''
COMBINED_VENOM = COMBINED_OWNED.replace(b'Habibi owned', b'Habibi Venom').replace(
    b'combined-selector-owned', b'combined-selector-venom').replace(
    b'DefaultSearch-Movies||{item_path}==DefaultSearch-TvShows',
    b'DefaultSearch-VenomMovies||{item_path}==DefaultSearch-VenomShows')
STANDARD_OWNED = COMBINED_OWNED.replace(b'combined/wall', b'standard').replace(
    b'combined-selector-owned', b'standard-selector-owned').replace(
    b'search_item_combined.xmltemplate', b'search_item_standard.xmltemplate').replace(
    b'<value name="hide_overlay">true</value>', b'<value name="show_overlay">true</value>')
STANDARD_VENOM = STANDARD_OWNED.replace(b'Habibi owned', b'Habibi Venom').replace(
    b'standard-selector-owned', b'standard-selector-venom').replace(
    b'DefaultSearch-Movies||{item_path}==DefaultSearch-TvShows',
    b'DefaultSearch-VenomMovies||{item_path}==DefaultSearch-VenomShows')

RATING_VARIABLE = b'''\n    <!-- Managed AM9 rating provenance: owned IMDb, TMDb, then community. -->
    <variable name="Label_Poster_Rating">
        <value condition="!String.IsEmpty(ListItem.Property(Habibi.Rating.IMDb))">$INFO[ListItem.Property(Habibi.Rating.IMDb),IMDb ]</value>
        <value condition="!String.IsEmpty(ListItem.Rating(imdb))">$INFO[ListItem.Rating(imdb),IMDb ]</value>
        <value condition="!String.IsEmpty(ListItem.Rating(tmdb))">$INFO[ListItem.Rating(tmdb),TMDb ]</value>
        <value condition="!String.IsEmpty(ListItem.Property(tmdb_id)) + !String.IsEmpty(ListItem.Rating)">$INFO[ListItem.Rating,TMDb ]</value>
        <value condition="!String.IsEmpty(ListItem.Property(Habibi.Rating.Community))">$INFO[ListItem.Property(Habibi.Rating.Community),\xe2\x98\x85 ]</value>
        <value condition="!String.IsEmpty(ListItem.Rating)">$INFO[ListItem.Rating,\xe2\x98\x85 ]</value>
    </variable>
'''
RATING_OBJECT = b'''    <include name="Object_PosterRating">
        <definition><control type="group">
            <right>12</right><bottom>12</bottom><width>132</width><height>40</height>
            <visible>[String.IsEqual(ListItem.DBType,movie) | String.IsEqual(ListItem.DBType,tvshow)] + !String.IsEmpty($VAR[Label_Poster_Rating])</visible>
            <control type="image"><texture border="18" colordiffuse="e6333333">common/box.png</texture></control>
            <control type="label"><font>font_hint_bold</font><align>center</align><aligny>center</aligny><textcolor>panel_fg_100</textcolor><label>$VAR[Label_Poster_Rating]</label></control>
        </control></definition>
    </include>
\n'''


def transform_search(data: bytes) -> bytes:
    # Combined and wall use this common include. Standard deliberately has no
    # Discover section upstream, so it gets only owned and Venom selectors.
    data = replace_once(data,
        b'<include name="Search_Switcher_Discover_Items">\n        <item>',
        b'<include name="Search_Switcher_Discover_Items">\n        <include>skinvariables-searchwidgets-combined-selector-owned</include>\n        <item>',
        'combined/wall owned selector')
    data = replace_once(data,
        b'<include>skinvariables-searchwidgets-combined-selector</include>',
        b'<include>skinvariables-searchwidgets-combined-selector-venom</include>',
        'combined/wall Venom selector')
    return replace_once(data,
        b'<include name="Search_Switcher_Standard_Items">\n        <include>skinvariables-searchwidgets-standard-selector</include>\n    </include>',
        b'<include name="Search_Switcher_Standard_Items">\n        <include>skinvariables-searchwidgets-standard-selector-owned</include>\n        <include>skinvariables-searchwidgets-standard-selector-venom</include>\n    </include>',
        'standard owned/Venom selectors')


def transform_hub(data: bytes) -> bytes:
    old = b'''<?xml version="1.0" encoding="UTF-8"?>
<window type="window" id="1107">
    <include>skinvariables-1107widgets-standard-onunload</include>
    <include content="Hub_Onload">
        <param name="window_id">1107</param>
    </include>
    <controls>
        <include content="Hub_Configurable_Window">
            <param name="window">1107</param>
        </include>
    </controls>
</window>
'''
    new = b'''<?xml version="1.0" encoding="UTF-8"?>
<window type="window" id="1107">
    <include>skinvariables-1107widgets-standard-onunload</include>
    <!-- Preserve generic Hub behaviour unless the managed profile selects Venom. -->
    <onload condition="Skin.String(HomeSwitcher.1107.Name,Venom TV) + System.HasAddon(plugin.video.venom.tv)">RunScript(special://home/addons/plugin.video.venom.tv/browser.py,live)</onload>
    <include content="Hub_Onload"><param name="window_id">1107</param></include>
    <controls>
        <include content="Hub_Configurable_Window" condition="!Skin.String(HomeSwitcher.1107.Name,Venom TV)"><param name="window">1107</param></include>
        <control type="button" id="990">
            <visible>Skin.String(HomeSwitcher.1107.Name,Venom TV) + System.HasAddon(plugin.video.venom.tv)</visible>
            <left>100</left><top>400</top><width>900</width><height>100</height>
            <font>font_main</font><label>Open Venom TV - Channels, Movies, Series, Favourites</label>
            <onclick>RunScript(special://home/addons/plugin.video.venom.tv/browser.py,live)</onclick>
        </control>
    </controls>
</window>
'''
    return replace_once(data, old, new, 'window 1107 Hub port')


def transform_ratings(root: Path) -> None:
    labels = root/'1080i/Includes_Labels.xml'; objects = root/'1080i/Includes_Objects.xml'; layouts = root/'1080i/Includes_Layouts.xml'
    labels.write_bytes(replace_once(labels.read_bytes(), b'    <variable name="Label_MediaList_Details_LeftLabel">', RATING_VARIABLE+b'\n    <variable name="Label_MediaList_Details_LeftLabel">', 'rating labels'))
    data = replace_once(objects.read_bytes(), b'    <include name="Object_AlphabetLetter_Label">', RATING_OBJECT+b'    <include name="Object_AlphabetLetter_Label">', 'rating object')
    data = replace_once(data, b'    <include name="Object_Indicator">\n        <param name="affix" />', b'    <include name="Object_Indicator">\n        <param name="poster_rating">false</param>\n        <param name="affix" />', 'rating indicator default')
    data = replace_once(data, b'                <nested />\n                <centerbottom>0</centerbottom>\n                <right>25</right>', b'                <nested />\n                <include content="Object_CenterBottom" condition="!$PARAM[poster_rating]"><param name="centerbottom">0</param></include>\n                <include content="Object_Bottom" condition="$PARAM[poster_rating]"><param name="bottom">52</param></include>\n                <right>25</right>', 'rating indicator position')
    objects.write_bytes(data)
    data = replace_once(layouts.read_bytes(), b'''                    <include condition="!$PARAM[selected] + $PARAM[indicator]" content="Object_Indicator">
                        <param name="affix">$PARAM[affix]</param>
                        <param name="listitem">$PARAM[listitem]</param>
                    </include>''', b'''                    <include condition="!$PARAM[selected] + $PARAM[indicator]" content="Object_Indicator">
                        <param name="affix">$PARAM[affix]</param>
                        <param name="listitem">$PARAM[listitem]</param>
                        <param name="poster_rating">!String.IsEmpty($VAR[Label_Poster_Rating])</param>
                    </include>''', 'rating indicator use')
    data = replace_once(data, b'                        <param name="focusbounce">true</param>\n                    </include>\n                </control>\n\n            </control>\n\n        </definition>\n    </include>\n\n    <include name="Layout_Reviews">', b'                        <param name="focusbounce">true</param>\n                    </include>\n                    <include content="Object_PosterRating" />\n                </control>\n\n            </control>\n\n        </definition>\n    </include>\n\n    <include name="Layout_Reviews">', 'poster rating layout')
    layouts.write_bytes(data)


def transform_actions(data: bytes) -> bytes:
    rule = b'''        <rule>
            <condition>{item_path}&lt;&lt;plugin://plugin.video.kodiseerr/</condition>
            <value><![CDATA[
                <onclick condition="String.Contains(ListItem.FolderPath,mode=request) | String.Contains(ListItem.FolderPath,mode=show_details)">RunPlugin($INFO[ListItem.FolderPath])</onclick>
                <onclick condition="!String.Contains(ListItem.FolderPath,mode=request) + !String.Contains(ListItem.FolderPath,mode=show_details) + ListItem.IsFolder">ActivateWindow(videos,$INFO[ListItem.FolderPath],return)</onclick>
                <onclick condition="!String.Contains(ListItem.FolderPath,mode=request) + !String.Contains(ListItem.FolderPath,mode=show_details) + !ListItem.IsFolder">PlayMedia($INFO[ListItem.FolderPath])</onclick>
            ]]></value>
        </rule>
'''
    return replace_once(data, b'    <rules name="widget_custom_onclick">\n        <rule>\n            <condition>{item_path}==Custom_Submenu</condition>', b'    <rules name="widget_custom_onclick">\n'+rule+b'        <rule>\n            <condition>{item_path}==Custom_Submenu</condition>', 'KodiSeerr widget actions')


def transform(root: Path) -> None:
    root = Path(root)
    if 'version="3.4.10"' not in (root/'addon.xml').read_text():
        raise RuntimeError('candidate is not Arctic Fuse 3.4.10')
    search = root/'1080i/Includes_Search.xml'; search.write_bytes(transform_search(search.read_bytes()))
    hub = root/'1080i/Custom_1107_Hub.xml'; hub.write_bytes(transform_hub(hub.read_bytes()))
    actions = root/'shortcuts/generator/data/setup/widgets_row.xml'; actions.write_bytes(transform_actions(actions.read_bytes()))
    data = root/'shortcuts/generator/data/base'
    for name, content in {'search_selector_owned.xml':COMBINED_OWNED, 'search_selector_venom.xml':COMBINED_VENOM, 'search_selector_standard_owned.xml':STANDARD_OWNED, 'search_selector_standard_venom.xml':STANDARD_VENOM}.items():
        target = data/name
        if target.exists(): raise RuntimeError('candidate unexpectedly owns '+name)
        target.write_bytes(content)
    config = root/'shortcuts/skinvariables-generator.json'
    config.write_bytes(replace_once(config.read_bytes(), b'        {"datafile": "generator/data/base/search_selector_standard.xml"},\n        {"datafile": "generator/data/base/search_info.xml"}', b'        {"datafile": "generator/data/base/search_selector_standard.xml"},\n        {"datafile": "generator/data/base/search_selector_owned.xml"},\n        {"datafile": "generator/data/base/search_selector_venom.xml"},\n        {"datafile": "generator/data/base/search_selector_standard_owned.xml"},\n        {"datafile": "generator/data/base/search_selector_standard_venom.xml"},\n        {"datafile": "generator/data/base/search_info.xml"}', 'SkinVariables selector datafiles'))
    transform_ratings(root)
