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

# The extra candidate plugins are likewise image-seeded only when their
# version-scoped directories do not already exist.  This keeps a mounted
# production-like config authoritative and makes the disposable all-plugin
# acceptance image self-contained without mounting host plugin artifacts.
if [ -d /opt/habibi-plugins ]; then
    for source in /opt/habibi-plugins/*; do
        [ -d "$source" ] || continue
        destination="${JELLYFIN_DATA_DIR:-/config}/plugins/$(basename "$source")"
        if [ ! -e "$destination" ]; then
            umask 022
            mkdir -p "$destination"
            cp -a "$source"/. "$destination"/
        fi
    done
fi

exec /jellyfin/jellyfin "$@"
