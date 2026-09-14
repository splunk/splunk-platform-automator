#!/usr/bin/env bash
# Install Splunk Platform Automator into a prefix (default ~/.local/spa).
#
# After a GitHub Release (gh auth for a private repo):
#   gh release download --repo splunk/splunk-platform-automator --pattern install.sh -O - | sh
#   curl -fsSL https://raw.githubusercontent.com/splunk/splunk-platform-automator/main/install.sh | sh
#
# From a checkout or extracted tarball:
#   ./install.sh --prefix ~/.local/spa
#   ./install.sh --from spa-framework-X.Y.Z.tar.gz
#
# Env: SPA_PREFIX, SPA_BINDIR, SPA_VERSION, GITHUB_TOKEN (download only; never printed).
set -euo pipefail

REPO="${SPA_REPO:-splunk/splunk-platform-automator}"
PREFIX="${SPA_PREFIX:-${HOME}/.local/spa}"
BINDIR="${SPA_BINDIR:-${HOME}/.local/bin}"
FROM=""
VERSION="${SPA_VERSION:-}"
SKIP_VENV=false
SKIP_DOCTOR=false
FORCE=false

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

usage() {
    cat <<EOF >&2
Usage: $0 [--prefix DIR] [--bindir DIR] [--from FILE] [--version X.Y.Z] [--force]
          [--skip-venv] [--skip-doctor]

  --prefix DIR     Install prefix / SPA_HOME (default: ~/.local/spa, or SPA_PREFIX)
  --bindir DIR     Directory for the spa wrapper on PATH (default: ~/.local/bin)
  --from FILE      Local spa-framework-*.tar.gz (skip GitHub download)
  --version VER    Release tag or X.Y.Z when downloading (default: latest)
  --force          Replace an existing prefix
  --skip-venv      Do not run spa_venv.sh --create
  --skip-doctor    Do not run spa doctor after install
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="${2:?}"; shift 2 ;;
        --bindir) BINDIR="${2:?}"; shift 2 ;;
        --from) FROM="${2:?}"; shift 2 ;;
        --version) VERSION="${2:?}"; shift 2 ;;
        --force) FORCE=true; shift ;;
        --skip-venv) SKIP_VENV=true; shift ;;
        --skip-doctor) SKIP_DOCTOR=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

PREFIX="${PREFIX/#\~/$HOME}"
BINDIR="${BINDIR/#\~/$HOME}"
if [[ "$PREFIX" != /* ]]; then
    PREFIX="$(pwd)/$PREFIX"
fi
if [[ "$BINDIR" != /* ]]; then
    BINDIR="$(pwd)/$BINDIR"
fi
if [[ "$PREFIX" == "$HOME" || "$PREFIX" == / ]]; then
    echo "ERROR: --prefix cannot be your home directory or /" >&2
    exit 1
fi

gh_ok() {
    command -v gh >/dev/null 2>&1 && gh auth status -h github.com >/dev/null 2>&1
}

is_spa_tree() {
    [[ -f "$1/ansible.cfg" && -x "$1/bin/spa" && -d "$1/ansible" ]]
}

copy_tree() {
    local src="$1" dest="$2"
    local manifest="$src/scripts/framework-files.txt"
    mkdir -p "$dest"
    if [[ -f "$manifest" ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" || "$line" == \#* ]] && continue
            [[ -e "$src/$line" ]] || continue
            dest_parent="$dest/$(dirname "$line")"
            mkdir -p "$dest_parent"
            rsync -a "$src/$line" "$dest_parent/"
        done < "$manifest"
    else
        rsync -a --exclude '.git/' --exclude 'tests/' --exclude '.github/' \
            --exclude 'config/' --exclude 'inventory/' --exclude '.venv/' \
            "$src/" "$dest/"
    fi
    rm -rf "$dest/config" "$dest/inventory" "$dest/tests" "$dest/.git" \
        "$dest/.venv" "$dest/saved_base_config_apps"
}

write_wrapper() {
    mkdir -p "$BINDIR"
    cat > "$BINDIR/spa" <<EOF
#!/usr/bin/env bash
export SPA_HOME=$(printf '%q' "$PREFIX")
venv="\$SPA_HOME/.venv/bin/python"
if [[ -x "\$venv" ]]; then
    exec "\$venv" "\$SPA_HOME/bin/spa" "\$@"
fi
exec "\$SPA_HOME/bin/spa" "\$@"
EOF
    chmod 0755 "$BINDIR/spa"
}

normalize_tag() {
    local ver="$1"
    case "$ver" in
        "") echo "" ;;
        v*) echo "$ver" ;;
        *) echo "v$ver" ;;
    esac
}

download_release() {
    local dest="$1"
    local tag
    tag="$(normalize_tag "$VERSION")"
    if [[ -z "$tag" ]]; then
        if gh_ok; then
            tag="$(gh release view --repo "$REPO" --json tagName -q .tagName)"
        elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
            tag="$(curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${REPO}/releases/latest" |
                python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag_name",""))')"
        else
            echo "ERROR: set --from FILE, or run gh auth login / set GITHUB_TOKEN to download a release." >&2
            exit 1
        fi
    fi
    [[ -n "$tag" ]] || { echo "ERROR: could not resolve a release tag" >&2; exit 1; }
    local ver="${tag#v}"
    local name="spa-framework-${ver}.tar.gz"
    echo "Downloading ${name} from ${REPO} ${tag}..."
    if gh_ok; then
        gh release download "$tag" --repo "$REPO" --pattern "$name" -D "$(dirname "$dest")"
        mv "$(dirname "$dest")/$name" "$dest"
        return
    fi
    if [[ -z "${GITHUB_TOKEN:-}" ]]; then
        echo "ERROR: need gh auth or GITHUB_TOKEN to download from a private repo." >&2
        exit 1
    fi
    local asset_url
    asset_url="$(curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/${REPO}/releases/tags/${tag}" |
        python3 -c '
import json, sys
want = sys.argv[1]
data = json.load(sys.stdin)
for asset in data.get("assets", []):
    if asset.get("name") == want:
        print(asset["url"])
        break
' "$name")"
    [[ -n "$asset_url" ]] || { echo "ERROR: release ${tag} has no asset ${name}" >&2; exit 1; }
    curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/octet-stream" -L -o "$dest" "$asset_url"
}

if [[ -e "$PREFIX" && "$FORCE" == true ]]; then
    rm -rf "$PREFIX"
elif [[ -e "$PREFIX" ]]; then
    if is_spa_tree "$PREFIX" || [[ -n "$(ls -A "$PREFIX" 2>/dev/null || true)" ]]; then
        echo "ERROR: ${PREFIX} already exists. Pass --force to replace it." >&2
        exit 2
    fi
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/spa-install.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

src=""
if [[ -n "$FROM" ]]; then
    FROM="${FROM/#\~/$HOME}"
    [[ -f "$FROM" ]] || { echo "ERROR: tarball not found: $FROM" >&2; exit 1; }
    mkdir -p "$tmp/tree"
    tar -xzf "$FROM" -C "$tmp/tree"
    src="$tmp/tree"
elif is_spa_tree "$(cd "$(dirname "$SELF")" && pwd)"; then
    src="$(cd "$(dirname "$SELF")" && pwd)"
else
    download_release "$tmp/spa-framework.tar.gz"
    mkdir -p "$tmp/tree"
    tar -xzf "$tmp/spa-framework.tar.gz" -C "$tmp/tree"
    src="$tmp/tree"
fi

if ! is_spa_tree "$src"; then
    echo "ERROR: archive or tree is missing ansible.cfg / bin/spa / ansible/" >&2
    exit 1
fi

mkdir -p "$PREFIX"
copy_tree "$src" "$PREFIX"
chmod 0755 "$PREFIX/bin/spa" "$PREFIX/bin/spa_venv.sh" || true
write_wrapper

if [[ "$SKIP_VENV" != true ]]; then
    echo "Creating virtualenv at ${PREFIX}/.venv ..."
    "$PREFIX/bin/spa_venv.sh" --create
fi

if [[ "$SKIP_DOCTOR" != true ]]; then
    "$BINDIR/spa" doctor --spa-home "$PREFIX" || \
        echo "spa doctor reported issues (install still completed)." >&2
fi

echo "SPA_HOME=${PREFIX}"
echo "Installed wrapper: ${BINDIR}/spa"
if ! echo ":${PATH}:" | grep -q ":${BINDIR}:"; then
    echo "Add ${BINDIR} to PATH, then: spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env"
else
    echo "Next: spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env"
fi
