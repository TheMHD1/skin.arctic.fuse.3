'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const { filterRequests, requestPrivacy } = require('./requestPrivacy');
const { patchIndex, patchRequest, build, PINS } = require('./build-overlay');
const Permission = { ADMIN: 2, MANAGE_REQUESTS: 16, REQUEST_VIEW: 16384 };
const request = (id, userId) => ({ id, type: 'tv', is4k: false,
  requestedBy: { id: userId, displayName: `Fixture ${userId}` }, seasons: [{ seasonNumber: 2 }],
  media: { id: 99, status: 4 } });
function user(id, mask = 32) {
  return { id, hasPermission: (bits, options) => {
    assert.equal(options.type, 'or');
    return Boolean(mask & Permission.ADMIN) || bits.some(bit => Boolean(mask & bit));
  } };
}
function respond(body, actor) {
  let sent, forwarded = 0;
  const res = { json(value) { sent = value; return this; } };
  requestPrivacy(Permission)({ user: actor }, res, error => {
    if (error) throw error;
    forwarded++;
  });
  assert.equal(forwarded, 1);
  assert.equal(res.json(body), res);
  return sent;
}
test('movie/TV/discover/media nested relations reveal only own requests without modifying source', () => {
  const body = { results: [{ mediaInfo: { status: 4, seasons: [{ seasonNumber: 3, status: 4 }],
    requests: [request(1, 7), request(2, 8)] } }], media: { requests: [request(3, 8)] } };
  const before = JSON.stringify(body);
  const filtered = respond(body, user(7));
  assert.deepEqual(filtered.results[0].mediaInfo.requests.map(r => r.id), [1]);
  assert.equal(filtered.results[0].mediaInfo.status, 4);
  assert.equal(filtered.results[0].mediaInfo.seasons[0].status, 4);
  assert.deepEqual(filtered.media.requests, []);
  assert.equal(JSON.stringify(body), before);
});
test('unknown/requesterless reduced relations fail closed, own string IDs work', () => {
  assert.deepEqual(filterRequests({ requests: [{ id: 1 }, { id: 2, requestedBy: { id: '7' } }] }, 7),
    { requests: [{ id: 2, requestedBy: { id: '7' } }] });
});
test('embedded single foreign request is redacted, standalone own requests remain intact', () => {
  assert.equal(respond({ issue: { request: request(1, 8) } }, user(7)).issue.request, null);
  assert.equal(respond(request(1, 7), user(7)).id, 1);
  assert.equal(respond(request(1, 8), user(7)), null);
});
test('native ADMIN, MANAGE_REQUESTS and REQUEST_VIEW preserve exact privileged payload', () => {
  const body = { requests: [request(1, 8)] };
  for (const bit of Object.values(Permission)) assert.equal(respond(body, user(7, bit)), body);
  assert.equal(respond(body, undefined), body);
});
test('serialization honors Date/toJSON and never mutates entity instances', () => {
  const date = new Date('2020-01-01T00:00:00Z');
  const entity = { toJSON() { return { mediaInfo: { requests: [request(1, 8)], status: 4 }, date }; } };
  assert.deepEqual(respond(entity, user(7)), { mediaInfo: { requests: [], status: 4 }, date: date.toJSON() });
});
test('user directory remains visible but another user requestCount is omitted', () => {
  const filtered = respond({ results: [
    { id: 7, displayName: 'Own fixture', requestCount: 2 },
    { id: 8, displayName: 'Other fixture', requestCount: 99 },
  ] }, user(7));
  assert.equal(filtered.results[0].requestCount, 2);
  assert.equal(filtered.results[1].displayName, 'Other fixture');
  assert.equal(Object.hasOwn(filtered.results[1], 'requestCount'), false);
});
test('invalid authenticated viewer identity refuses wrapping', () => {
  let error;
  requestPrivacy(Permission)({ user: user('bad') }, {}, value => { error = value; });
  assert.match(error.message, /valid authenticated user/);
});
test('hook is inserted immediately after authentication and rebasing drift is rejected', () => {
  const base = 'router.use(auth_1.checkUser);\nrouter.use("/movie", movieRoutes);';
  assert.match(patchIndex(base), /checkUser\);\nrouter.use\(require/);
  assert.throws(() => patchIndex('changed source'), /rebase required/);
  assert.throws(() => patchIndex(base + base), /ambiguous/);
});
test('count query joins viewer before getCount; later where calls cannot erase restriction', () => {
  const source = "requestRoutes.get('/count', async (_req, res, next) => {\n" +
    "    const query = requestRepository\n            .createQueryBuilder('request')\n" +
    "            .innerJoinAndSelect('request.media', 'media');\n        const totalCount = await query.getCount();\n" +
    "    query.where('request.type = :type', {type: 'tv'}); return totalCount;\n});";
  const patched = patchRequest(source);
  const run = async actor => {
    let handler;
    const joins = [];
    const query = { innerJoinAndSelect() { return this; },
      innerJoin(...args) { joins.push(args); return this; },
      getCount() { return joins.length ? 2 : 10; }, where() { return this; } };
    vm.runInNewContext(patched, { requestRoutes: { get(_path, fn) { handler = fn; } },
      requestRepository: { createQueryBuilder() { return query; } }, permissions_1: { Permission } });
    const count = await handler({ user: actor }, {}, () => {});
    return { count, joins };
  };
  return Promise.all([run(user(7)), run(user(1, 2))]).then(([limited, privileged]) => {
    assert.equal(limited.count, 2);
    assert.equal(limited.joins[0][3].privacyUserId, 7);
    assert.equal(privileged.count, 10);
    assert.equal(privileged.joins.length, 0);
  });
});
test('builder refuses wrong version and altered reviewed input before creating output', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'seerr-privacy-test-'));
  try {
    fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ name: 'seerr', version: '9.0.0' }));
    const output = path.join(root, 'stage');
    assert.throws(() => build(root, output), /Unsupported Seerr/);
    fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ name: 'seerr', version: '3.4.1' }));
    fs.mkdirSync(path.join(root, 'dist/routes'), { recursive: true });
    fs.writeFileSync(path.join(root, 'dist/routes/index.js'), 'drift');
    assert.throws(() => build(root, output), /Unreviewed source drift/);
    assert.equal(fs.existsSync(output), false);
  } finally { fs.rmSync(root, { recursive: true }); }
});
test('optional real clean-source build passes syntax and guard, guard refuses changed file/version', {
  skip: !process.env.SEERR_PRIVACY_CLEAN_APP,
}, () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'seerr-privacy-clean-'));
  try {
    const stage = path.join(root, 'stage');
    build(process.env.SEERR_PRIVACY_CLEAN_APP, stage);
    fs.copyFileSync(path.join(process.env.SEERR_PRIVACY_CLEAN_APP, 'package.json'), path.join(stage, 'package.json'));
    fs.mkdirSync(path.join(stage, 'dist/lib'), { recursive: true });
    fs.copyFileSync(path.join(process.env.SEERR_PRIVACY_CLEAN_APP, 'dist/lib/permissions.js'), path.join(stage, 'dist/lib/permissions.js'));
    for (const name of ['dist/routes/index.js', 'dist/routes/request.js', 'dist/middleware/requestPrivacy.js']) {
      assert.equal(spawnSync(process.execPath, ['--check', path.join(stage, name)]).status, 0);
    }
    const guard = () => spawnSync(process.execPath, [path.join(stage, 'privacy-startup-guard.js')],
      { env: { ...process.env, SEERR_PRIVACY_APP_ROOT: stage } });
    assert.equal(guard().status, 0);
    fs.appendFileSync(path.join(stage, 'dist/middleware/requestPrivacy.js'), '\n// drift\n');
    assert.notEqual(guard().status, 0);
    assert.equal(Object.keys(PINS).length, 3);
  } finally { fs.rmSync(root, { recursive: true }); }
});
