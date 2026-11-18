#!/usr/bin/env bash
# Build the operator framework tarball (no tests/, .git, or lab config).
# Usage: scripts/pack-framework.sh [-o FILE]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
OUT=""
MANIFEST="$ROOT/scripts/framework-files.txt"

usage() {
    cat <<EOF >&2
Usage: $0 [-o FILE]

  Default output: spa-framework-${VERSION}.tar.gz in the current directory.
  The archive has no wrapping directory: extract into SPA_HOME.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output)
            OUT="${2:?--output needs a path}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$OUT" ]]; then
    OUT="spa-framework-${VERSION}.tar.gz"
fi
if [[ "$OUT" != /* ]]; then
    OUT="$(pwd)/$OUT"
fi

stage="$(mktemp -d "${TMPDIR:-/tmp}/spa-pack.XXXXXX")"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT

mkdir -p "$stage"
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    src="$ROOT/$line"
    if [[ ! -e "$src" ]]; then
        echo "ERROR: missing pack path: $line" >&2
        exit 1
    fi
    dest_parent="$stage/$(dirname "$line")"
    mkdir -p "$dest_parent"
    rsync -a "$src" "$dest_parent/" || exit 1
done < "$MANIFEST"

# Never ship operator lab state even if a local clone has it.
rm -rf "$stage/config" "$stage/inventory" "$stage/tests" "$stage/.git" \
    "$stage/.venv" "$stage/.collections" "$stage/saved_base_config_apps" \
    "$stage/.cursor/plans" "$stage/.github"

export COPYFILE_DISABLE=1
tar -C "$stage" -czf "$OUT" .
echo "$OUT"
