#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const VERSION = '3.4.1';
const PINS = {
  'dist/routes/index.js': '56a862cf0ff33e92b9b28436fa361212f8ce838cd64e2abeba6ecaa0048c565d',
  'dist/routes/request.js': '69b60eae98e0ad6577fadebbf649313834a69e29fce1c94dfa46762f0c976bd4',
  'dist/lib/permissions.js': '28de58d420ae96a5b3529eaa9c98ebfd86d6bc6cdc0dba74901bcc7396e378ca',
};
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
function replaceOnce(source, anchor, replacement) {
  if (source.split(anchor).length !== 2) throw new Error('Source anchor missing or ambiguous; rebase required');
  return source.replace(anchor, replacement);
}
function patchIndex(source) {
  return replaceOnce(source, 'router.use(auth_1.checkUser);',
    'router.use(auth_1.checkUser);\nrouter.use(require("../middleware/requestPrivacy").requestPrivacy(permissions_1.Permission));');
}
function patchRequest(source) {
  source = replaceOnce(source, "requestRoutes.get('/count', async (_req, res, next) => {",
    "requestRoutes.get('/count', async (req, res, next) => {");
  const anchor = "            .innerJoinAndSelect('request.media', 'media');\n        const totalCount = await query.getCount();";
  return replaceOnce(source, anchor, "            .innerJoinAndSelect('request.media', 'media');\n" +
    "        if (!req.user?.hasPermission([permissions_1.Permission.MANAGE_REQUESTS, permissions_1.Permission.REQUEST_VIEW], { type: 'or' })) {\n" +
    "            query.innerJoin('request.requestedBy', 'privacyRequester', 'privacyRequester.id = :privacyUserId', { privacyUserId: req.user.id });\n" +
    "        }\n        const totalCount = await query.getCount();");
}
function build(appRoot, outputRoot) {
  const pkg = JSON.parse(fs.readFileSync(path.join(appRoot, 'package.json'), 'utf8'));
  if (pkg.name !== 'seerr' || pkg.version !== VERSION) throw new Error('Unsupported Seerr version; rebase required');
  const inputs = {};
  for (const [name, hash] of Object.entries(PINS)) {
    const bytes = fs.readFileSync(path.join(appRoot, name));
    if (digest(bytes) !== hash) throw new Error(`Unreviewed source drift: ${name}`);
    inputs[name] = bytes.toString('utf8');
  }
  if (fs.existsSync(outputRoot)) throw new Error('Output must be a new staging directory');
  const payload = {
    'dist/routes/index.js': patchIndex(inputs['dist/routes/index.js']),
    'dist/routes/request.js': patchRequest(inputs['dist/routes/request.js']),
    'dist/middleware/requestPrivacy.js': fs.readFileSync(path.join(__dirname, 'requestPrivacy.js')),
  };
  // Startup guard checks the image's native permission semantics as well as all overlays.
  const expected = { ...PINS };
  for (const [name, bytes] of Object.entries(payload)) expected[name] = digest(bytes);
  const guard = `'use strict';\nconst fs = require('node:fs');\nconst crypto = require('node:crypto');\nconst path = require('node:path');\nconst root = process.env.SEERR_PRIVACY_APP_ROOT || '/app';\nconst expected = ${JSON.stringify(expected, null, 2)};\nconst pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));\nif (pkg.name !== 'seerr' || pkg.version !== '${VERSION}') throw new Error('Seerr privacy: unsupported image version; rebase required');\nfor (const [name, hash] of Object.entries(expected)) {\n  const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex');\n  if (actual !== hash) throw new Error('Seerr privacy: source/overlay drift in ' + name + '; rebase required');\n}\n`;
  payload['privacy-startup-guard.js'] = guard;
  // Create files exclusively. The builder only touches the caller's new stage.
  fs.mkdirSync(outputRoot, { recursive: true });
  for (const [name, bytes] of Object.entries(payload)) {
    const target = path.join(outputRoot, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, bytes, { flag: 'wx', mode: 0o644 });
  }
  fs.writeFileSync(path.join(outputRoot, 'manifest.json'), JSON.stringify({
    version: VERSION, upstream: PINS, files: Object.fromEntries(
      Object.entries(payload).map(([name, bytes]) => [name, digest(bytes)])),
  }, null, 2) + '\n', { flag: 'wx' });
  return expected;
}
if (require.main === module) {
  if (process.argv.length !== 4) {
    console.error('Usage: node build-overlay.js CLEAN_APP_ROOT NEW_STAGING_ROOT');
    process.exit(2);
  }
  try { build(path.resolve(process.argv[2]), path.resolve(process.argv[3])); console.log('Built guarded Seerr 3.4.1 privacy overlay'); }
  catch (error) { console.error(error.message); process.exit(1); }
}
module.exports = { build, patchIndex, patchRequest, PINS, VERSION, digest };
