#!/bin/sh
# Install Splunk Platform Automator into a prefix.
# Default SPA_HOME: ${XDG_DATA_HOME:-$HOME/.local/share}/spa
# Default launcher: $HOME/.local/bin/spa
#
# From 3.0, install.sh is a GitHub Release asset (not a git-branch URL):
#   curl -fsSL https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh | sh
# Flags when piping:  curl … | sh -s -- --prefix DIR
#
# From a checkout or extracted tarball:
#   ./install.sh
#   ./install.sh --from spa-framework-X.Y.Z.tar.gz --prefix /opt/spa
#
# Env: SPA_PREFIX, SPA_BINDIR, SPA_VERSION, XDG_DATA_HOME, GITHUB_TOKEN (download only; never printed).
set -eu

REPO="${SPA_REPO:-splunk/splunk-platform-automator}"
PREFIX="${SPA_PREFIX:-}"
BINDIR="${SPA_BINDIR:-}"
FROM=""
VERSION="${SPA_VERSION:-}"
SKIP_VENV=false
SKIP_DOCTOR=false
FORCE=false
UNINSTALL=false
YES=false

# Piped `curl | sh` has no real script path ($0 is sh / -).
SELF=""
case "$0" in
    -|sh|dash|ash|bash|*"/sh"|*"/dash"|*"/ash"|*"/bash")
        ;;
    *)
        if [ -f "$0" ]; then
            case "$0" in
                /*) SELF="$0" ;;
                *) SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")" ;;
            esac
        fi
        ;;
esac

expand_tilde() {
    _p=$1
    case "$_p" in
        "~") printf '%s' "$HOME" ;;
        ~/*) printf '%s' "$HOME/${_p#~/}" ;;
        *) printf '%s' "$_p" ;;
    esac
}

usage() {
    cat <<EOF >&2
Usage: $0 [--prefix DIR] [--bindir DIR] [--from FILE] [--version X.Y.Z] [--force]
          [--skip-venv] [--skip-doctor]
       $0 --uninstall [--yes] [--prefix DIR] [--bindir DIR]

  --prefix DIR     Install prefix / SPA_HOME (default: \${XDG_DATA_HOME:-~/.local/share}/spa, or SPA_PREFIX)
  --bindir DIR     Directory for the spa wrapper on PATH (default: ~/.local/bin, or SPA_BINDIR)
  --from FILE      Local spa-framework-*.tar.gz (skip GitHub download)
  --version VER    Release tag or X.Y.Z when downloading (default: latest)
  --force          Replace an existing prefix
  --skip-venv      Do not run spa_venv.sh --create
  --skip-doctor    Do not run spa doctor after install
  --uninstall      Remove the prefix and matching PATH wrapper (not env dirs or AWS)
  -y, --yes        Confirm uninstall (required in agent mode)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="${2:?}"; shift 2 ;;
        --bindir) BINDIR="${2:?}"; shift 2 ;;
        --from) FROM="${2:?}"; shift 2 ;;
        --version) VERSION="${2:?}"; shift 2 ;;
        --force) FORCE=true; shift ;;
        --skip-venv) SKIP_VENV=true; shift ;;
        --skip-doctor) SKIP_DOCTOR=true; shift ;;
        --uninstall) UNINSTALL=true; shift ;;
        -y|--yes) YES=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

xdg_data_home() {
    # XDG Base Directory Spec: ignore a relative XDG_DATA_HOME.
    case "${XDG_DATA_HOME:-}" in
        /*) printf '%s' "$XDG_DATA_HOME" ;;
        *) printf '%s' "${HOME}/.local/share" ;;
    esac
}

if [ -z "$PREFIX" ]; then
    PREFIX="$(xdg_data_home)/spa"
else
    PREFIX="$(expand_tilde "$PREFIX")"
fi
if [ -z "$BINDIR" ]; then
    BINDIR="${HOME}/.local/bin"
else
    BINDIR="$(expand_tilde "$BINDIR")"
fi
case "$PREFIX" in
    /*) ;;
    *) PREFIX="$(pwd)/$PREFIX" ;;
esac
case "$BINDIR" in
    /*) ;;
    *) BINDIR="$(pwd)/$BINDIR" ;;
esac
if [ "$PREFIX" = "$HOME" ] || [ "$PREFIX" = / ]; then
    echo "ERROR: --prefix cannot be your home directory or /" >&2
    exit 1
fi

gh_ok() {
    command -v gh >/dev/null 2>&1 && gh auth status -h github.com >/dev/null 2>&1
}

is_spa_tree() {
    [ -f "$1/ansible.cfg" ] && [ -x "$1/bin/spa" ] && [ -d "$1/ansible" ]
}

is_agent() {
    [ -n "${SPA_AGENT:-}" ] && return 0
    [ -n "${CLAUDECODE:-}" ] && return 0
    [ -n "${CLAUDE_CODE:-}" ] && return 0
    [ -n "${CURSOR_AGENT:-}" ] && return 0
    [ -n "${CURSOR_TRACE_ID:-}" ] && return 0
    [ -n "${CODEX_THREAD_ID:-}" ] && return 0
    return 1
}

wrapper_matches_prefix() {
    wrap="$BINDIR/spa"
    [ -f "$wrap" ] || return 1
    grep -Fq "$PREFIX" "$wrap"
}

confirm_uninstall() {
    if [ "$YES" = true ]; then
        return 0
    fi
    if is_agent; then
        echo "ERROR: uninstall requires --yes in agent mode" >&2
        exit 1
    fi
    echo "uninstall will remove:" >&2
    echo "$PREFIX" >&2
    echo "$BINDIR/spa" >&2
    printf 'Proceed? [y/N] ' >&2
    ans=""
    read -r ans || true
    case "$ans" in
        y|Y|yes|YES) return 0 ;;
        *)
            echo "ERROR: uninstall cancelled" >&2
            exit 1
            ;;
    esac
}

do_uninstall() {
    confirm_uninstall
    if [ -e "$PREFIX" ] && ! is_spa_tree "$PREFIX"; then
        echo "ERROR: ${PREFIX} is not an SPA install prefix (need ansible.cfg, bin/spa, ansible/)." >&2
        echo "Refusing to delete it. This is not spa destroy; env dirs and AWS are untouched." >&2
        exit 1
    fi
    wrap="$BINDIR/spa"
    if wrapper_matches_prefix; then
        rm -f "$wrap"
        echo "Removed wrapper: ${wrap}"
    elif [ -e "$wrap" ]; then
        echo "Leaving ${wrap} (not the wrapper for ${PREFIX})" >&2
    fi
    if [ -e "$PREFIX" ]; then
        rm -rf "$PREFIX"
        echo "Removed prefix: ${PREFIX}"
    else
        echo "Prefix already absent: ${PREFIX}"
    fi
}

if [ "$UNINSTALL" = true ]; then
    do_uninstall
    exit 0
fi

copy_tree() {
    src="$1"
    dest="$2"
    manifest="$src/scripts/framework-files.txt"
    mkdir -p "$dest"
    if [ -f "$manifest" ]; then
        while IFS= read -r line || [ -n "$line" ]; do
            [ -z "$line" ] && continue
            case "$line" in
                \#*) continue ;;
            esac
            [ -e "$src/$line" ] || continue
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
    quoted=$(printf '%s' "$PREFIX" | sed "s/'/'\\\\''/g")
    cat > "$BINDIR/spa" <<EOF
#!/bin/sh
export SPA_HOME='$quoted'
venv="\$SPA_HOME/.venv/bin/python"
if [ -x "\$venv" ]; then
    exec "\$venv" "\$SPA_HOME/bin/spa" "\$@"
fi
exec "\$SPA_HOME/bin/spa" "\$@"
EOF
    chmod 0755 "$BINDIR/spa"
}

normalize_tag() {
    ver="$1"
    case "$ver" in
        "") echo "" ;;
        v*) echo "$ver" ;;
        *) echo "v$ver" ;;
    esac
}

download_release() {
    dest="$1"
    tag="$(normalize_tag "$VERSION")"
    if [ -z "$tag" ]; then
        if gh_ok; then
            tag="$(gh release view --repo "$REPO" --json tagName -q .tagName)"
        elif [ -n "${GITHUB_TOKEN:-}" ]; then
            tag="$(curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${REPO}/releases/latest" |
                python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag_name",""))')"
        else
            echo "ERROR: set --from FILE, or run gh auth login / set GITHUB_TOKEN to download a release." >&2
            exit 1
        fi
    fi
    [ -n "$tag" ] || { echo "ERROR: could not resolve a release tag" >&2; exit 1; }
    ver="${tag#v}"
    name="spa-framework-${ver}.tar.gz"
    echo "Downloading ${name} from ${REPO} ${tag}..."
    if gh_ok; then
        gh release download "$tag" --repo "$REPO" --pattern "$name" -D "$(dirname "$dest")"
        mv "$(dirname "$dest")/$name" "$dest"
        return
    fi
    if [ -z "${GITHUB_TOKEN:-}" ]; then
        echo "ERROR: need gh auth or GITHUB_TOKEN to download from a private repo." >&2
        exit 1
    fi
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
    [ -n "$asset_url" ] || { echo "ERROR: release ${tag} has no asset ${name}" >&2; exit 1; }
    curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/octet-stream" -L -o "$dest" "$asset_url"
}

if [ -e "$PREFIX" ] && [ "$FORCE" = true ]; then
    rm -rf "$PREFIX"
elif [ -e "$PREFIX" ]; then
    if is_spa_tree "$PREFIX" || [ -n "$(ls -A "$PREFIX" 2>/dev/null || true)" ]; then
        echo "ERROR: ${PREFIX} already exists. Pass --force to replace it." >&2
        exit 2
    fi
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/spa-install.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

src=""
if [ -n "$FROM" ]; then
    FROM="$(expand_tilde "$FROM")"
    [ -f "$FROM" ] || { echo "ERROR: tarball not found: $FROM" >&2; exit 1; }
    mkdir -p "$tmp/tree"
    tar -xzf "$FROM" -C "$tmp/tree"
    src="$tmp/tree"
elif [ -n "$SELF" ] && is_spa_tree "$(cd "$(dirname "$SELF")" && pwd)"; then
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

if [ "$SKIP_VENV" != true ]; then
    echo "Creating virtualenv at ${PREFIX}/.venv ..."
    "$PREFIX/bin/spa_venv.sh" --create
fi

if [ "$SKIP_DOCTOR" != true ]; then
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
