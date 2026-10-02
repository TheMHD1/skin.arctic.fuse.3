"""Additive empty-list focus repair after remote UI reliability revision 2."""
import hashlib

BEFORE = '4ce2230ac470a80f5480cdedda9a4c5c57e804895cc3841929b47336333a82a8'


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Unreviewed remote browser anchor')
    return source.replace(old, new)


def browser(source):
    source = replace(source,
        '            if self.category is None:\n                self.setFocusId(910)',
        '            if self.category is None:\n                self.setFocusId(910 if self.categories else 901)')
    source = replace(source,
        "            self.render();self.setFocusId(920)\n            self.getControl(920).selectItem(getattr(self,'last_grid_position',0))",
        '            self.render()\n'
        '            if self.visible_entries:\n'
        '                self.setFocusId(920)\n'
        "                self.getControl(920).selectItem(min(getattr(self,'last_grid_position',0),len(self.visible_entries)-1))\n"
        '            else:self.setFocusId(910 if self.categories else 901)')
    source = replace(source,
        '        self.getControl(910).selectItem(0);self.setFocusId(910)\n        if self.pending_bookmark:',
        '        if categories:\n'
        '            self.getControl(910).selectItem(0);self.setFocusId(910)\n'
        '        else:\n'
        '            self.setFocusId(901)\n'
        "            self.getControl(940).setLabel('No categories available. Choose a section to retry, or press Back.')\n"
        '        if self.pending_bookmark and categories:')
    source = replace(source,
        '            self.load_entries();self.setFocusId(920)\n        # No automatic category fetch',
        '            self.focus_grid_when_ready=True\n            self.load_entries()\n        # No automatic category fetch')
    source = replace(source,
        "        self.getControl(940).setLabel('Loading…')\n        self.entries=[];self.visible_entries=[];self.getControl(920).reset()",
        # Leave the populated grid BEFORE reset; defer its restoration until
        # the accepted generation has populated it. This covers series Back,
        # sort/filter and refresh, not just the category OK path repaired in r2.
        "        self.getControl(940).setLabel('Loading…')\n"
        '        if self.getFocusId()==920:\n'
        '            self.focus_grid_when_ready=True\n'
        '            self.setFocusId(910 if self.categories else 901)\n'
        '        self.entries=[];self.visible_entries=[];self.getControl(920).reset()')
    source = replace(source,
        "        if snapshot.get('restore_grid_position') is not None:",
        "        if self.visible_entries and snapshot.get('restore_grid_position') is not None:")
    source = replace(source,
        "                self.kind={901:'live',902:'movie',903:'series',904:'favorites'}[control];self.load_categories();self.setFocusId(910)",
        "                self.kind={901:'live',902:'movie',903:'series',904:'favorites'}[control]\n"
        '                self.setFocusId(control);self.load_categories()')
    source = replace(source,
        "                self.query=query.strip();self.page=0;self.native_offset=0;self.load_entries();self.setFocusId(920)",
        "                self.query=query.strip();self.page=0;self.native_offset=0\n"
        '                self.focus_grid_when_ready=True\n'
        '                self.setFocusId(910 if self.categories else 901);self.load_entries()')
    compile(source, 'remote-browser', 'exec')
    return source


def transform(data):
    if hashlib.sha256(data).hexdigest() != BEFORE:
        raise ValueError('Unreviewed remote browser source')
    return browser(data.decode()).encode()
