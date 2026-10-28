#!/usr/bin/env bash
# Build the version-scoped Jellyfin Web 12.4 candidate in a disposable clone.
# It deliberately refuses any other source revision: the retained patches are
# source patches, not a generic overlay for arbitrary Jellyfin Web versions.
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 /path/to/jellyfin-web-v12.4-checkout" >&2
    exit 64
fi

web_root=$1
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# candidate-12.4 -> jellyfin-custom -> server -> integration.
integration_root=$(cd -- "$script_root/../../.." && pwd)
expected=0a580ce8df89282dfd120b6d5efb8e106da23bd5

actual=$(git -C "$web_root" rev-parse HEAD)
if [[ $actual != "$expected" ]]; then
    echo "refusing Jellyfin Web $actual; expected exact v12.4 $expected" >&2
    exit 65
fi

patches=(
    "$integration_root/web-navigation/search-jellyfin-web-12.1.patch"
    "$integration_root/web-home-library/jellyfin-web-12.1-owned-home.patch"
)

for patch in "${patches[@]}"; do
    if [[ ! -f $patch ]]; then
        echo "missing required maintained patch: $patch" >&2
        exit 66
    fi
    git -C "$web_root" apply --check "$patch"
done
for patch in "${patches[@]}"; do
    git -C "$web_root" apply "$patch"
done

cd "$web_root"
npm ci --no-audit --no-fund
npm run build:check
npx vitest run \
    src/apps/legacy/features/search/api/fetchScopedMedia.test.ts \
    src/components/homesections/sections/ownedHomeLogic.test.ts \
    --config vite.config.ts
npm run build:production

echo "PASS: exact Jellyfin Web 12.4 custom search/home candidate built in $web_root/dist"
