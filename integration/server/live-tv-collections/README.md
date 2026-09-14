# Local category/collection extension

These files overlay upstream JeKaQM/jellyfin-live-tv-category-browser version 0.3.0.0 for Jellyfin 12.0.0. They are not a new upstream version.

Copy CategorySnapshots.cs, ChannelCollectionFile.cs and LiveTvCategoryIndex.cs into Jellyfin.Plugin.LiveTvCategories/Services/. Copy ChannelCollectionTests.cs into the matching test project. Also retain the earlier administrator maintenance controller in ../VenomCategoryMaintenanceController.cs under Controllers/.

Build with the .NET 10 SDK and the upstream project/package pins. The production package retains upstream's bundled web files and the local navigation script. Place channel-collections.json beside the plugin DLL using venom-publish-collections.py on CT102. Do not put provider credentials or seed ledgers in this public repository.

Category JSON uses provider_order (array of exact group names) and groups (id, name, channels containing native Jellyfin id). Curated membership never bypasses user-visible channel filtering. Unknown channel IDs are omitted. Invalid local configuration falls back to normal channels.

Back up the DLL before replacement and restart Jellyfin once to load it. Removing channel-collections.json reverts curated ordering at next cache rebuild, without deleting any native channels or favourites. Current status: [remaining work](../../VENOM-REMAINING-WORK.md).

Kodi integration is deployed and maintained in `../../plugin.video.venom.tv/`;
see [package guide](../../VENOM-PACKAGE.md). Do not reapply the old pending patch.
Ugoos was updated, verified, and powered off at the user's request.

Pinned upstream source commit: `580a46e5d77655d6bfe4f00621524dbd808f9cc7`.
`test-project.patch` includes the matching Jellyfin 12 test dependencies and
provider-order regression. Apply it from the upstream repository root, then
copy the overlays and both extra test files. Run the test project with .NET 10.
The tests simulate removal from the tuner snapshot and restoration with the
same ID, including user visibility restrictions. They do **not** prove a real
Dispatcharr hide/restore has propagated through a Jellyfin guide refresh.
