# Isolated acceptance — September 26, 2026

Executed against the already-local Jellyfin 12.1 custom image, using temporary
fixture configuration/media, real native APIs, and actual maintained publishers.
No production writes, production database or production credentials were used.

- Immutable image ID:
  `sha256:8bde9abf947274579f13231ec818293b478587191859383682c1b2a7527934ec`
- Plugin 1.2.0.0 DLL SHA-256:
  `82fa3cbed39050135239667082d4e115e7faf4dc9973bb4984f2130362354f79`
- Native source pin: `ee91c75e777da41a9c4f4855e70adc604fbf2ef8`.

The four no-service safety tests passed. The real-server run passed eleven
acceptance assertions: new movie and series episode playable file-source
indexing; separate Movie/Series provider-ID seed, plugin idempotency and
conflicting-ID rejection; duplicate events for each type; actual raw-arrival
worker publication of Arabic subtitle A and atomic replacement B with native
normalized SRT verification and VTT serving; durable outbox acknowledgement;
unchanged unrelated anchor identities/media sources; and native rejection of
unauthenticated discovery.

At each assertion the global `RefreshLibrary` task was Idle and its complete
`LastExecutionResult` matched the initial fixture scan's result. The default
cleanup removed the exact generated container, internal network, loopback relay
and fixture media/config; no library scan was started during publication.

Native Jellyfin skips wholly empty physical roots during its initial scan.
Therefore two unrelated anchors were created during the permitted bootstrap
scan to establish real parent Folder identities. Tested imports were created
only after that baseline. This proves established-library publication, not
brand-new-empty-library commissioning.

This is synthetic SDR and real indexing/subtitle HTTP acceptance, not ARR-hook,
download-client, GPU generation, physical playback or client UI acceptance.
See [README.md](README.md) for rerun/update gates and private-artifact handling.
The run emits source SHA-256 fingerprints and rejects mid-run source drift;
future image/plugin/source changes require this acceptance to be repeated.

## Final rerun — September 26, 2026

The final disposable-fixture rerun passed all eleven assertions again, followed
by all four `test_harness.py` safety tests. Cleanup completed: the owned
container, internal network, loopback relay and temporary fixture directory
were removed. The final immutable evidence was:

- Image ID: `sha256:8bde9abf947274579f13231ec818293b478587191859383682c1b2a7527934ec`
- Plugin DLL SHA-256: `82fa3cbed39050135239667082d4e115e7faf4dc9973bb4984f2130362354f79`
- Reconciler SHA-256: `125a57e9ac6076a984b6397d752da0e5a0ee9f5c01b5694d92d0d5c2948bb0d9`
- Raw arrival SHA-256: `1df363c2564ab68deaec60c14fdfb51436c9cdcfac53dd64c9531f3e14a2e921`
- Managed publication queue SHA-256: `f40d07e1f3a7befa51ad199e85147433b259e7ff39392a3c94f6828fab788295`
- Jellyfin sync SHA-256: `47d836e6f813c97dc9c9bb7084d047f0ce8ac98e795eba2dceea0ce37e17db62`
- Shared subtitle-view filter SHA-256: `5a33de4ba08428d76fc22dfa705869ef8206132848c75bf01882f225758bd2a2`

This E2E run proves native indexing, exact raw-subtitle refresh/serving,
replacement, outbox acknowledgement and the no-global-scan invariant in the
isolated server. It is distinct from the 46 focused reconciler/unit regression
tests, which cover durable link-commit marker and acknowledgement race behavior
at the state-transition level. Neither evidence substitutes for ARR-hook,
production-data, GPU/model, client playback or physical display acceptance.
