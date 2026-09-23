/* Run against the patched Enhanced source; no browser/dependencies required. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = process.argv[2];
if (!root) throw new Error('Usage: node test-search-priority.cjs /path/to/patched/je-source');
const source = fs.readFileSync(path.join(root, 'Jellyfin.Plugin.JellyfinEnhanced/js/jellyseerr/ui/ui-results.js'), 'utf8');
const start = source.indexOf('        const primaryCardTypes');
const end = source.indexOf('\n        positionSection();', start);
assert(start > 0 && end > start, 'exact reviewed placement code must exist');
const code = source.slice(start, end);
function runCase(types, expected) {
    const list = [];
    const section = {name: 'Discover'};
    const move = (node, at) => {
        const old = list.indexOf(node);
        if (old >= 0) { list.splice(old, 1); if (old < at) at--; }
        list.splice(at, 0, node);
        node.parentElement = container;
    };
    const node = (name, type, venom = false) => ({
        name, type, venom,
        classList: {contains: c => c === 'verticalSection'},
        matches: () => venom,
        querySelector: () => type ? {dataset: {type}} : null,
        after: n => move(n, list.indexOf(list.find(v => v.name === name)) + 1),
        before: n => move(n, list.indexOf(list.find(v => v.name === name)))
    });
    types.forEach(([name, type, venom]) => list.push(node(name, type, venom)));
    const container = {
        get lastElementChild() { return list.at(-1); },
        appendChild: n => move(n, list.length)
    };
    Object.defineProperties(section, {
        previousElementSibling: {get: () => list[list.indexOf(section) - 1]},
        nextElementSibling: {get: () => list.includes(section) ? list[list.indexOf(section) + 1] : null}
    });
    const page = {
        querySelectorAll: q => q.startsWith('.verticalSection') ? list.filter(n => n !== section) : [],
        querySelector: q => q.startsWith('.noItemsMessage') ? null : q.startsWith('[data-habibi') ? list.find(n => n.venom) : container
    };
    const context = {searchPage: page, sectionToInject: section};
    vm.createContext(context);
    vm.runInContext(code + '\npositionSection(); positionSection();', context);
    assert.deepEqual(list.map(n => n.name), expected);
}
runCase([['Movies', 'Movie'], ['Shows', 'Series'], ['Venom', 'Movie', true]], ['Movies', 'Shows', 'Discover', 'Venom']);
runCase([['Venom', 'Movie', true]], ['Discover', 'Venom']);
runCase([['Movies', 'Movie']], ['Movies', 'Discover']);
runCase([['People', 'Person'], ['Venom', 'Series', true]], ['People', 'Discover', 'Venom']);
runCase([], ['Discover']);
console.log('Search priority: five placement/idempotence cases passed');
