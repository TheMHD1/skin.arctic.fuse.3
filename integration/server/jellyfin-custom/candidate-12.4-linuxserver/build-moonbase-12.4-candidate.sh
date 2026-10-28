#!/usr/bin/env bash
# Rebuild the retained Moonbase/Moonfin server port for Jellyfin 12.4.
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "usage: $0 /private/output-dir" >&2; exit 64
fi
out=$1
[[ $out = /* ]] || { echo "output must be an absolute path" >&2; exit 65; }
mkdir -p "$out"
[[ -z $(find "$out" -mindepth 1 -print -quit) ]] || { echo "refusing non-empty output" >&2; exit 66; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
src="$root/moonbase-12.4-source"
manifest="$root/moonbase-12.4-source.sha256"
[[ -f "$src/Jellyfin/backend/Moonfin.Server.csproj" && -f "$manifest" ]] || exit 65
python3 "$root/verify-moonbase-source.py"
tmpbase=${TMPDIR:-/tmp}
mkdir -p "$tmpbase"
stage=$(mktemp -d "$tmpbase/moonbase-12.4.XXXXXX")
trap 'rm -rf "$stage"' EXIT
python3 "$root/verify-moonbase-source.py" --copy-to "$stage"
rg -q '<TargetFramework>net10.0</TargetFramework>' "$src/Jellyfin/backend/Moonfin.Server.csproj"
rg -q 'Jellyfin.Controller" Version="12.4.0"' "$src/Jellyfin/backend/Moonfin.Server.csproj"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e DOTNET_CLI_HOME=/tmp -e NUGET_PACKAGES=/tmp/nuget -v "$stage:/src" -v "$out:/out" -w /src/Jellyfin \
  mcr.microsoft.com/dotnet/sdk@sha256:4beef5b8919dcaa2dc924233bd069257e883cc7a061e09088a97d152d6a48510 sh -ec '
    mkdir -p /tmp/nuget &&
    dotnet test tests/Moonfin.Server.Tests/Moonfin.Server.Tests.csproj -c Release &&
    dotnet publish backend/Moonfin.Server.csproj -c Release -f net10.0 -o /out'
(cd "$out" && find . -type f ! -name artifacts.sha256 -print0 | sort -z | xargs -0 sha256sum) > "$out/artifacts.sha256"
(cd "$out" && sha256sum --check artifacts.sha256)
