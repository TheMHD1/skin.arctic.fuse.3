# Library Experience 12.4 compile candidate

This project compiles the existing plugin source against only Jellyfin 12.4
revision `83d0d0e7f76e23e2e085c8ff67d28b772d35967d`. It deliberately does not
modify the established 12.1 source guard. Before building, apply
`library-experience-12.4-guard.patch` to a disposable copy of the plugin
source; that candidate accepts **exactly 12.4.0.0**, not a version range.

Build with `JellyfinSourceRoot` set to the patched disposable 12.4 checkout
and direct all outputs outside this repository. The 12.4 guard and the server
revision guard are independent hard gates. A successful compile is an ABI gate;
the runtime image acceptance is recorded in the adjacent server candidate.
