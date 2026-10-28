# Dispatcharr 0.33 semantic-port candidate

Target: official `v0.33.0`, commit
`2fa13a6707bdf0dae87e0c494bcd3ca282cdeb3e`; verified official image
`ghcr.io/dispatcharr/dispatcharr:0.33.0` digest
`sha256:96bc548978c68e684677da7895692eeeefb7f0b2edfa38311dac2b702c61d236`.

`dispatcharr-0.33-habibi.patch` is the semantic port of all four maintained
0.31 patches. It deliberately does not force-apply the old hunks. Apply only
to that exact release with:

```sh
git apply --check integration/server/dispatcharr-candidate-0.33/dispatcharr-0.33-habibi.patch
git apply integration/server/dispatcharr-candidate-0.33/dispatcharr-0.33-habibi.patch
```

## Preserved behavior

- Redacts synthetic/transformed XC credential URLs and transform inputs from
  this live transform path; supports `.ts` to `.m3u8` transport rewrites
  against current account credentials and the real stream ID.
- Fails closed for new shared-provider owners if Redis/lock acquisition is
  unavailable; ordinary contention remains a follower path.
- Emits a standards-valid 188-byte MPEG-TS null packet for a quiet attached
  client. Keepalive is downstream-client state, not an inference from the
  owner worker's upstream health.
- Uses a bounded 3–15 second capacity-admission budget based on shutdown grace;
  it never releases/preempts another viewer's slot.
- Allows authenticated XC `HEAD` probes, returning only transport metadata and
  never invoking `stream_ts`, registering a client, or reserving a provider
  stream.

## Validation performed

- `git apply --check` passed on a fresh official v0.33.0 checkout.
- Python compilation and `git diff --check` passed.
- In a disposable official AIO image with a fresh named data volume, the
  focused Django suite passed: **58 tests** in 0.166 seconds:

  ```text
  apps.m3u.tests.test_credential_transform
  apps.channels.tests.test_ts_proxy_keepalive
  apps.proxy.live_proxy.tests.test_xc_hls
  apps.proxy.live_proxy.tests.test_habibi_033_regressions
  ```

`test_habibi_033_regressions.py` is retained beside the patch for easy review;
the same file is included by the patch.

## Deployment gate

This is source-only. Before a live update, snapshot the Dispatcharr data,
build an image from the exact patched tree, and run a disposable smoke test for
native PVR, XC TS/HLS and a provider-capacity follower. Do not reuse the
disposable test volume or copy any provider configuration into source.

The upstream release has unrelated URL-bearing log sites, including VOD and
input-manager diagnostics. This candidate eliminates credential exposure in
the maintained transform path; it is not a claim that upstream has a complete
repository-wide URL-redaction policy. Treat a broader log-redaction audit as a
separate security change so it can be reviewed without widening this media
compatibility update.
