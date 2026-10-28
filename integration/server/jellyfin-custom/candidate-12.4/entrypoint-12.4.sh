#!/bin/sh
set -eu

# A mounted /config hides image-layer plugin files. Seed the version-scoped
# plugin only when it is absent; never overwrite an administrator-managed DLL.
plugin_dir="${JELLYFIN_DATA_DIR:-/config}/plugins/LibraryExperience"
plugin_dll="$plugin_dir/Jellyfin.Plugin.LibraryExperience.dll"
if [ ! -e "$plugin_dll" ]; then
    umask 022
    mkdir -p "$plugin_dir"
    cp /opt/habibi-plugin/Jellyfin.Plugin.LibraryExperience.dll "$plugin_dll"
    cp /opt/habibi-plugin/meta.json "$plugin_dir/meta.json"
fi

exec /jellyfin/jellyfin "$@"
