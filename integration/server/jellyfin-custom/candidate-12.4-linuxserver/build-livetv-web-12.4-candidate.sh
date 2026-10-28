#!/usr/bin/env bash
# Build the Live TV Categories Web client from one exact Jellyfin Web 12.4
# revision.  The resulting dist is placed in the Live TV plugin's `web/`
# directory by the caller; it intentionally contains both the general Habibi
# Home/search changes and the category route overlay, because this plugin
# serves a complete Web bundle rather than a small incremental asset.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 /path/to/pristine-jellyfin-web-v12.4-checkout [plugin-web-output]" >&2
    exit 64
fi

web_root=$1
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
integration_root=$(cd -- "$script_root/../../.." && pwd)
expected_revision=0a580ce8df89282dfd120b6d5efb8e106da23bd5
overlay_root="$script_root/live-tv-web-12.4-overlay"

actual_revision=$(git -C "$web_root" rev-parse HEAD)
if [[ $actual_revision != "$expected_revision" ]]; then
    echo "refusing Jellyfin Web $actual_revision; expected exact 12.4 $expected_revision" >&2
    exit 65
fi
if [[ -n $(git -C "$web_root" status --porcelain) ]]; then
    echo "refusing non-pristine Jellyfin Web checkout" >&2
    exit 68
fi
for required in "$overlay_root/index.tsx" \
    "$overlay_root/categories/LiveTvCategoriesView.tsx" \
    "$overlay_root/categories/liveTvCategories.ts" \
    "$overlay_root/categories/useLiveTvCategories.ts" \
    "$overlay_root/categories/liveTvCategories.test.ts" \
    "$overlay_root/library/LibraryPage.tsx" \
    "$overlay_root/library/LibraryPage.test.ts" \
    "$overlay_root/library/liveTvCategoryTab.ts" \
    "$integration_root/web-navigation/search-jellyfin-web-12.1.patch" \
    "$integration_root/web-home-library/jellyfin-web-12.1-owned-home.patch"; do
    [[ -f $required ]] || { echo "missing maintained input: $required" >&2; exit 66; }
done

patches=(
    "$integration_root/web-navigation/search-jellyfin-web-12.1.patch"
    "$integration_root/web-home-library/jellyfin-web-12.1-owned-home.patch"
)
for patch in "${patches[@]}"; do
    git -C "$web_root" apply --check "$patch"
done
for patch in "${patches[@]}"; do
    git -C "$web_root" apply "$patch"
done
install -D -m 0644 "$overlay_root/index.tsx" \
    "$web_root/src/apps/modern/routes/livetv/index.tsx"
install -D -m 0644 "$overlay_root/library/LibraryPage.tsx" \
    "$web_root/src/apps/modern/features/libraries/components/LibraryPage.tsx"
install -D -m 0644 "$overlay_root/library/LibraryPage.test.ts" \
    "$web_root/src/apps/modern/features/libraries/components/LibraryPage.test.ts"
install -D -m 0644 "$overlay_root/library/liveTvCategoryTab.ts" \
    "$web_root/src/apps/modern/features/libraries/components/liveTvCategoryTab.ts"
for source in "$overlay_root"/categories/*; do
    install -D -m 0644 "$source" \
        "$web_root/src/apps/modern/routes/livetv/categories/$(basename "$source")"
done

cd "$web_root"
npm ci --no-audit --no-fund
npx tsc --noEmit
npx vitest run \
    src/apps/legacy/features/search/api/fetchScopedMedia.test.ts \
    src/components/homesections/sections/ownedHomeLogic.test.ts \
    src/apps/modern/features/libraries/components/LibraryPage.test.ts \
    src/apps/modern/routes/livetv/categories/liveTvCategories.test.ts \
    --config vite.config.ts
npm run build:production

if [[ $# -eq 2 ]]; then
    mkdir -p "$2"
    if [[ -n $(find "$2" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
        echo "refusing non-empty plugin Web output directory" >&2
        exit 69
    fi
    cp -a "$web_root/dist/." "$2/"
    (cd "$web_root/dist" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$2/.dist-sha256"
    # The shell opens .package-sha256 before find runs, so exclude both
    # generated manifests. Otherwise the package listing hashes itself and can
    # never equal the source dist manifest.
    (cd "$2" && find . -type f ! -name .dist-sha256 ! -name .package-sha256 -print0 | sort -z | xargs -0 sha256sum) > "$2/.package-sha256"
    diff -u "$2/.dist-sha256" "$2/.package-sha256" || { echo "plugin bundle differs from dist" >&2; exit 70; }
fi

printf 'PASS: merged 12.4 Live TV Web bundle: %s/dist/index.html\n' "$web_root"
