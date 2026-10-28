# Read-only live plugin inventory — pre-12.4

This inventory is from `/data/config/jellyfin/data/plugins` on the Media LXC.
No config XML, databases, accounts, tokens or plugin cache were copied.

| Installed directory | Plugin metadata ABI | Candidate status |
| --- | --- | --- |
| AniDB 13.0.0.0 | 12.0.0.0 | Official artifact loaded in blank 12.4 candidate |
| Anime Filler Marker 1.0.0.3 | 12.0.0.0 | Official artifact + declared HtmlAgilityPack dependency loaded |
| Artwork 3.0.0.0 | 12.0.0.0 | Official artifact loaded in blank 12.4 candidate |
| Chapter Segments Provider 5.0.0.0 | 12.0.0.0 | Official artifact loaded in blank 12.4 candidate |
| Fanart 15.0.0.0 | 12.0.0.0 | Official artifact loaded in blank 12.4 candidate |
| Intro Skipper 12.0.5.0 | 12.0.0.0 | Candidate 12.0.6 built/loaded, FFmpeg path verified |
| Jellyfin Enhanced 12.7.0.0 | 12.0.0.0 | Candidate 12.13 built/loaded |
| Kodi Sync Queue 16.0.0.0 | 12.0.0.0 | Candidate built/loaded with LiteDB |
| Library Experience 1.2.0.0 | 12.1.0.0 | Custom 12.4-guarded candidate built/loaded |
| Live TV Categories 0.3.0.0 | 12.0.0.0 | Custom Venom backend + merged 12.4 category Web bundle built/loaded |
| Local Intros 5.0.0.0 | 12.0.0.0 | Official artifact loaded in blank 12.4 candidate |
| Moonbase 2.4.0.0 | 12.1.0.0 | Custom 12.4 port built/loaded; authenticated Seerr route fixture passed |
| Playback Reporting 19.0.0.0 | 12.0.0.0 | Official artifact loaded in blank 12.4 candidate |
| Reports 19.0.0.0 | 12.0.0.0 | Official Reports 20 artifact loaded in blank 12.4 candidate |

Configuration-only XML exists for other historical components including AniList,
AudioDb, CustomTabs, FileTransformation, JellyTweaks, MusicBrainz, OMDb,
StudioImages, TMDbBoxSets, Tmdb, Tvdb and Shokofin. They are not installed
plugin evidence and must neither be copied to a blank candidate nor used to
infer a currently enabled feature.

The metadata ABI is a plugin-declared minimum compatibility target, not proof
that a plugin is safe with every later server release. The all-14 blank
candidate load verifies discovery and startup on Jellyfin 12.4 only; it does
not replace the stopped-config canary and feature acceptance checks required
for provider credentials, existing configuration and user-visible workflows.
