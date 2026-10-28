'use strict';
// Execute only inside the pinned disposable Seerr image with no production
// mounts or external network. Uses native routes, entities and permissions.
const assert = require('node:assert/strict');
const { once } = require('node:events');
if (process.env.NODE_ENV !== 'test') throw new Error('Fixture requires NODE_ENV=test');
if (require('/app/package.json').version !== '3.5.1') throw new Error('Wrong image');
require('/app/privacy-startup-guard.js');
const express = require('/app/node_modules/express');
const db = require('/app/dist/datasource').default;
const { User } = require('/app/dist/entity/User');
const Media = require('/app/dist/entity/Media').default;
const { MediaRequest } = require('/app/dist/entity/MediaRequest');
const { Permission } = require('/app/dist/lib/permissions');
const { getSettings } = require('/app/dist/lib/settings');
const router = require('/app/dist/routes').default;
const key = 'synthetic-fixture-only';
let server;
async function seed(entity, values) {
  // No subscribers, notifications or ARR writes while seeding fake data.
  await db.createQueryBuilder().insert().into(entity).values(values).callListeners(false).execute();
}
async function main() {
  assert.equal(db.options.type, 'sqlite');
  assert.equal(db.options.database, ':memory:');
  await db.initialize();
  const settings = getSettings();
  settings.main = { ...settings.main, apiKey: key };
  settings.radarr = [];
  settings.sonarr = [];
  await seed(User, [
    { id: 1, email: 'owner@fixture.invalid', username: 'owner', avatar: '', permissions: Permission.ADMIN },
    { id: 2, email: 'first@fixture.invalid', username: 'first', avatar: '', permissions: Permission.REQUEST },
    { id: 3, email: 'second@fixture.invalid', username: 'second', avatar: '', permissions: Permission.REQUEST },
  ]);
  await seed(Media, { id: 1, mediaType: 'movie', tmdbId: 12345, status: 5, status4k: 1 });
  await seed(MediaRequest, [
    { id: 1, status: 1, type: 'movie', media: { id: 1 }, requestedBy: { id: 2 }, is4k: false },
    { id: 2, status: 2, type: 'movie', media: { id: 1 }, requestedBy: { id: 3 }, is4k: false },
  ]);
  const app = express();
  app.use(express.json());
  app.use('/api/v1', router);
  app.use((error, _req, res, _next) => res.status(error.status || 500).json({ message: error.message }));
  server = app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = 'http://127.0.0.1:' + server.address().port + '/api/v1';
  async function get(route, actor, status = 200) {
    const headers = actor === null ? {} : { 'X-API-Key': key, 'X-API-User': String(actor) };
    const response = await fetch(base + route, { headers, signal: AbortSignal.timeout(10000) });
    const body = await response.json();
    assert.equal(response.status, status, route + ': ' + JSON.stringify(body));
    return body;
  }
  const owner = await get('/request', 1);
  assert.deepEqual(owner.results.map(row => row.id).sort(), [1, 2]);
  for (const [actor, own, foreign] of [[2, 1, 2], [3, 2, 1]]) {
    const list = await get('/request', actor);
    assert.deepEqual(list.results.map(row => row.id), [own]);
    const count = await get('/request/count', actor);
    assert.equal(count.total, 1);
    assert.equal((await get('/request/' + own, actor)).id, own);
    await get('/request/' + foreign, actor, 403);
    await get('/user/' + (actor === 2 ? 3 : 2) + '/requests', actor, 403);
  }
  assert.equal((await get('/request/count', 1)).total, 2);
  await get('/request', null, 403);
  // Native entities/relations and availability must not be mutated by filtering.
  const media = await db.getRepository(Media).findOne({ where: { id: 1 }, relations: { requests: { requestedBy: true } } });
  assert.equal(media.status, 5);
  assert.equal(media.requests.length, 2);
  const { filterRequests } = require('/app/dist/middleware/requestPrivacy');
  const filtered = filterRequests(JSON.parse(JSON.stringify(media)), 2);
  assert.deepEqual(filtered.requests.map(row => row.id), [1]);
  assert.equal(media.requests.length, 2);
  console.log('PASS: native3.5.1 routes/auth/owner/ordinary/count/detail/foreign-denial; shared availability and ORM relations retained');
}
main().then(() => process.exitCode = 0).catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  if (server) await new Promise(resolve => server.close(resolve));
  if (db.isInitialized) await db.destroy();
  // Native modules may own background timers; do not leave a fixture resident.
  process.exit(process.exitCode || 0);
});
