# Live TV Categories 12.4 source-preserving candidate

The candidate starts from upstream commit
`580a46e5d77655d6bfe4f00621524dbd808f9cc7` and preserves the local Venom
services, maintenance controller and regression tests from
`integration/server/live-tv-collections/`. It changes only the compile-time
Jellyfin Controller/Model package references from `12.0.0` to `12.4.0`.

In a blank SDK container (`mcr.microsoft.com/dotnet/sdk:10.0`), the overlaid
plugin and test project compiled and all **35/35** tests passed. The resulting
code-only DLL SHA-256 was
`e443eb709af8a74ab27cacf769cfefd250b566e2ff779c5c5aeb48f4f0a5c524`.

This proves the custom server component can compile and retain its unit-level
Venom behavior. It still requires inclusion with the semantic 12.4 Web port,
then a blank LinuxServer runtime load and an authenticated Live TV canary.
