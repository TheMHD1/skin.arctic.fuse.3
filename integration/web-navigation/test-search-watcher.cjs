/* Bounded, coalesced watcher; run against the complete patched Enhanced input. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(process.argv[2], 'Jellyfin.Plugin.JellyfinEnhanced/js/jellyseerr/ui/ui-results.js'), 'utf8');
const start = source.indexOf('        function stopReposition()');
const end = source.indexOf('\n    };', start);
assert(start > 0 && end > start);
function fixture() {
    const frames = new Map(), timers = new Map();
    let id = 0, callback, observer, positioned = 0;
    const context = {
        pendingRepositionObserver: null, pendingRepositionTimeout: null, pendingRepositionFrame: null,
        sectionToInject: {isConnected: true}, searchPage: {isConnected: true},
        MutationObserver: function(cb) {
            callback = cb; observer = this; this.disconnected = false;
            this.observe = () => {}; this.disconnect = () => {this.disconnected = true;};
        },
        requestAnimationFrame: cb => {const next = ++id; frames.set(next, cb); return next;},
        cancelAnimationFrame: key => frames.delete(key),
        setTimeout: (cb, ms) => {const next = ++id; timers.set(next, {cb, ms}); return next;},
        clearTimeout: key => timers.delete(key),
        positionSection: () => positioned++
    };
    vm.createContext(context);vm.runInContext(source.slice(start, end), context);
    return {context, frames, timers, mutate: () => callback(), observer: () => observer,
        positioned: () => positioned,
        frame: () => {const [key, cb] = frames.entries().next().value; frames.delete(key); cb();}};
}
{
    const f = fixture();
    for(let i = 0; i < 100; i++) f.mutate();
    assert.equal(f.frames.size, 1);assert.equal(f.positioned(), 0);
    f.frame();assert.equal(f.positioned(), 1);
    f.mutate();f.frame();assert.equal(f.positioned(), 2);
    assert.equal([...f.timers.values()][0].ms, 30000);
    // A response arriving after the old five-second cutoff still repositions.
    assert.equal(f.observer().disconnected, false);
}
{
    const f = fixture();f.mutate();f.context.sectionToInject.isConnected = false;f.frame();
    assert.equal(f.positioned(), 0);assert.equal(f.observer().disconnected, true);
    assert.equal(f.frames.size, 0);assert.equal(f.timers.size, 0);
    assert.equal(f.context.pendingRepositionObserver, null);
}
{
    const f = fixture();f.mutate();[...f.timers.values()][0].cb();
    assert.equal(f.observer().disconnected, true);assert.equal(f.frames.size, 0);
    assert.equal(f.context.pendingRepositionTimeout, null);
}
{
    const f = fixture();f.mutate();
    const begin = source.indexOf('        if (pendingRepositionObserver) {');
    const finish = source.indexOf("        searchPage.querySelectorAll('.jellyseerr-section')", begin);
    vm.runInContext(source.slice(begin, finish), f.context);
    assert.equal(f.observer().disconnected, true);assert.equal(f.frames.size, 0);assert.equal(f.timers.size, 0);
}
console.log('Search watcher: coalescing, delayed response, detach, deadline and replacement passed');
