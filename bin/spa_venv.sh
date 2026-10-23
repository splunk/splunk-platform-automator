#!/usr/bin/env bash
# ==============================================================================
# Shared Python virtualenv for Splunk Platform Automator.
# One implementation for the framework, env dirs, and the test runners.
# ==============================================================================
# Usage:
#   source bin/spa_venv.sh                  # activate (create when missing)
#   source bin/spa_venv.sh --no-create      # activate only if it already exists
#   ./bin/spa_venv.sh --create              # create when missing, then exit
#   ./bin/spa_venv.sh --reinstall           # install requirements into existing venv
#   ./bin/spa_venv.sh --upgrade             # upgrade packages and collections in place
#   ./bin/spa_venv.sh --rebuild             # recreate and install requirements
#   ./bin/spa_venv.sh --path                # print the resolved venv directory
#
# Venv resolution (first match wins):
#   1. --dir DIR  or  SPA_VENV_DIR
#   2. ENV/.venv when it exists (--env DIR, or SPA_ENV_DIR)  -> pin per env
#   3. SPA_HOME/.venv                                        -> shared default
#
# Ansible collections install next to the venv (<venv parent>/.collections)
# so an env venv and the shared venv never fight over ~/.ansible.
# ==============================================================================

_spa_venv_self="${BASH_SOURCE[0]}"
_spa_venv_sourced=false
if [[ "$_spa_venv_self" != "${0}" ]]; then
    _spa_venv_sourced=true
fi

_spa_venv_bin_dir="$(cd "$(dirname "$_spa_venv_self")" && pwd)"
_spa_venv_home="${SPA_HOME:-$(cd "${_spa_venv_bin_dir}/.." && pwd)}"

_spa_venv_dir=""
_spa_venv_env="${SPA_ENV_DIR:-}"
_spa_venv_python="${SPA_VENV_PYTHON:-python3}"
_spa_venv_python_explicit=false
if [[ -n "${SPA_VENV_PYTHON:-}" ]]; then
    _spa_venv_python_explicit=true
fi
_spa_venv_mode="activate"
_spa_venv_create=true
_spa_venv_install=true
_spa_venv_reinstall=false
_spa_venv_upgrade=false
_spa_venv_rebuild=false
_spa_venv_reqs=()
_spa_venv_pkgs=()
_spa_venv_rc=0

_spa_venv_usage() {
    cat <<'EOF'
Usage: spa_venv.sh [options] [pip-package ...]

  --dir DIR            Use this venv directory
  --env DIR            Env dir; DIR/.venv wins over the shared venv
  --python PATH        Interpreter used when creating (default: python3)
  --requirements FILE  Requirements file (repeatable; default SPA_HOME/requirements.txt)
  --create             Create/update the venv and exit
  --reinstall          Create if missing; reinstall requirements, then exit
  --upgrade            Create if missing; upgrade packages and collections, then exit
  --rebuild            Delete/recreate the venv and install requirements
  --no-create          Activate only when the venv already exists
  --no-install         Create the venv without pip/galaxy installs
  --path               Print the resolved venv directory and exit
  -h, --help           This help
EOF
}

# Bail out without killing an interactive shell when sourced.
_spa_venv_fail() {
    echo "$1" >&2
    _spa_venv_rc=1
}

# Progress on stderr so spa can show steps while pip stays quiet on stdout.
_spa_venv_progress() {
    echo "$1" >&2
}

# ansible-core 2.21 crashes on startup under Python 3.15: it patches
# dataclasses._is_type, which 3.15 removed. 2.22 is the first release that
# supports 3.15, and it is not published yet. Prints old, new, or ok.
_spa_venv_python_band() {
    "$1" -c 'import sys
v = sys.version_info[:2]
raise SystemExit(print("old" if v < (3, 9) else "new" if v >= (3, 15) else "ok"))'
}

_spa_venv_choose_python() {
    local band candidate version
    band="$(_spa_venv_python_band "$_spa_venv_python" 2>/dev/null || true)"
    [[ "$band" == "new" ]] || return 0
    if [[ "$_spa_venv_python_explicit" == true ]]; then
        _spa_venv_fail "spa_venv: ${_spa_venv_python} is Python 3.15 or newer. Ansible 2.21 runs on Python 3.9 through 3.14. Pass --python python3.14."
        return 1
    fi
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        band="$(_spa_venv_python_band "$candidate" 2>/dev/null || true)"
        [[ "$band" == "ok" ]] || continue
        "$candidate" -c 'import venv' >/dev/null 2>&1 || continue
        version="$("$candidate" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
        _spa_venv_progress "Using Python ${version} (${candidate}). Ansible 2.21 does not run on Python 3.15 or newer."
        _spa_venv_python="$candidate"
        return 0
    done
    _spa_venv_fail "spa_venv: python3 is Python 3.15 or newer, and no Python 3.9 through 3.14 interpreter is on PATH. Install Python 3.14 and rerun, or pass --python python3.14."
    return 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            [[ $# -ge 2 ]] || { _spa_venv_fail "--dir needs a value"; break; }
            _spa_venv_dir="$2"
            shift 2
            ;;
        --env)
            [[ $# -ge 2 ]] || { _spa_venv_fail "--env needs a value"; break; }
            _spa_venv_env="$2"
            shift 2
            ;;
        --python)
            [[ $# -ge 2 ]] || { _spa_venv_fail "--python needs a value"; break; }
            _spa_venv_python="$2"
            _spa_venv_python_explicit=true
            shift 2
            ;;
        --requirements)
            [[ $# -ge 2 ]] || { _spa_venv_fail "--requirements needs a value"; break; }
            _spa_venv_reqs+=("$2")
            shift 2
            ;;
        --create)
            _spa_venv_mode="create"
            shift
            ;;
        --reinstall)
            _spa_venv_mode="create"
            _spa_venv_reinstall=true
            shift
            ;;
        --upgrade)
            _spa_venv_mode="create"
            _spa_venv_reinstall=true
            _spa_venv_upgrade=true
            shift
            ;;
        --rebuild)
            _spa_venv_mode="create"
            _spa_venv_reinstall=true
            _spa_venv_rebuild=true
            shift
            ;;
        --no-create)
            _spa_venv_create=false
            shift
            ;;
        --no-install)
            _spa_venv_install=false
            shift
            ;;
        --path)
            _spa_venv_mode="path"
            shift
            ;;
        -h|--help)
            _spa_venv_usage
            _spa_venv_mode="help"
            break
            ;;
        -*)
            _spa_venv_fail "Unknown option: $1"
            break
            ;;
        *)
            _spa_venv_pkgs+=("$1")
            shift
            ;;
    esac
done

if [[ $_spa_venv_rc -eq 0 && "$_spa_venv_mode" != "help" ]]; then
    # Resolve the venv directory.
    if [[ -z "$_spa_venv_dir" ]]; then
        _spa_venv_dir="${SPA_VENV_DIR:-}"
    fi
    if [[ -z "$_spa_venv_dir" && -n "$_spa_venv_env" && -d "${_spa_venv_env}/.venv" ]]; then
        _spa_venv_dir="${_spa_venv_env}/.venv"
    fi
    if [[ -z "$_spa_venv_dir" ]]; then
        _spa_venv_dir="${_spa_venv_home}/.venv"
    fi
    if [[ "$_spa_venv_dir" != /* ]]; then
        _spa_venv_dir="$(pwd)/${_spa_venv_dir}"
    fi

    if [[ ${#_spa_venv_reqs[@]} -eq 0 && -f "${_spa_venv_home}/requirements.txt" ]]; then
        _spa_venv_reqs=("${_spa_venv_home}/requirements.txt")
    fi
fi

if [[ $_spa_venv_rc -eq 0 && "$_spa_venv_mode" == "path" ]]; then
    echo "$_spa_venv_dir"
    _spa_venv_mode="done"
fi

if [[ $_spa_venv_rc -eq 0 && "$_spa_venv_mode" != "done" && "$_spa_venv_mode" != "help" ]]; then
    if [[ "$_spa_venv_rebuild" == true && -d "$_spa_venv_dir" ]]; then
        _spa_venv_progress "Rebuilding virtual environment..."
        rm -rf "$_spa_venv_dir"
    fi

    # A directory without bin/activate is a half-created venv (interrupted or
    # failed install); rebuild it rather than sourcing something broken.
    if [[ -d "$_spa_venv_dir" && ! -f "${_spa_venv_dir}/bin/activate" ]]; then
        if [[ "$_spa_venv_create" == true ]]; then
            _spa_venv_progress "Recreating incomplete virtual environment..."
            rm -rf "$_spa_venv_dir"
        fi
    fi

    if [[ ! -d "$_spa_venv_dir" ]]; then
        if [[ "$_spa_venv_create" != true ]]; then
            echo "spa_venv: no venv at ${_spa_venv_dir} (create it with: ${_spa_venv_bin_dir}/spa_venv.sh --create)" >&2
            _spa_venv_mode="done"
        else
            _spa_venv_choose_python
        fi
        if [[ $_spa_venv_rc -ne 0 || "$_spa_venv_mode" == "done" ]]; then
            :
        elif ! command -v "$_spa_venv_python" >/dev/null 2>&1; then
            _spa_venv_fail "spa_venv: interpreter not found: ${_spa_venv_python}"
        elif ! "$_spa_venv_python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
            _spa_venv_fail "spa_venv: ${_spa_venv_python} must be Python 3.9+ with the venv module"
        elif ! "$_spa_venv_python" -c 'import venv'; then
            _spa_venv_fail "spa_venv: ${_spa_venv_python} has no venv module (install python3-venv / python3)"
        else
            _spa_venv_progress "Creating virtual environment..."
            if ! "$_spa_venv_python" -m venv "$_spa_venv_dir"; then
                _spa_venv_fail "spa_venv: could not create ${_spa_venv_dir}"
            else
                _spa_venv_fresh=true
            fi
        fi
    fi
fi

if [[ $_spa_venv_rc -eq 0 && "$_spa_venv_mode" != "done" && "$_spa_venv_mode" != "help" ]]; then
    if [[ -f "${_spa_venv_dir}/bin/activate" ]]; then
        # shellcheck disable=SC1090
        source "${_spa_venv_dir}/bin/activate"
    else
        _spa_venv_fail "spa_venv: incomplete venv at ${_spa_venv_dir} (recreate it with: ${_spa_venv_bin_dir}/spa_venv.sh --create)"
    fi
fi

if [[ $_spa_venv_rc -eq 0 && "$_spa_venv_mode" != "done" && "$_spa_venv_mode" != "help" && "$_spa_venv_install" == true ]]; then
    if [[ "${_spa_venv_fresh:-false}" == true || "$_spa_venv_reinstall" == true ]]; then
        _spa_venv_progress "Installing pip..."
        pip install -q --upgrade pip
        for _spa_venv_req in "${_spa_venv_reqs[@]}"; do
            [[ -f "$_spa_venv_req" ]] || continue
            if [[ "$_spa_venv_upgrade" == true ]]; then
                _spa_venv_progress "Upgrading packages..."
                pip install -q --upgrade -r "$_spa_venv_req"
            else
                _spa_venv_progress "Installing packages..."
                pip install -q -r "$_spa_venv_req"
            fi
        done
    fi
    if [[ ${#_spa_venv_pkgs[@]} -gt 0 ]]; then
        if [[ "$_spa_venv_upgrade" == true ]]; then
            pip install -q --upgrade "${_spa_venv_pkgs[@]}"
        else
            pip install -q "${_spa_venv_pkgs[@]}"
        fi
    fi

    # Verify the capability SPA actually needs. This catches unsupported
    # Python/Ansible combinations and incomplete manual venvs without encoding
    # every future compatibility boundary in the command paths.
    if [[ -x "${_spa_venv_dir}/bin/ansible-inventory" ]]; then
        _spa_venv_probe_tmp="$(mktemp -d "${TMPDIR:-/tmp}/spa-ansible-probe.XXXXXX")"
        if ! ANSIBLE_LOCAL_TEMP="$_spa_venv_probe_tmp" ANSIBLE_REMOTE_TEMP="$_spa_venv_probe_tmp" \
             python -c 'from ansible.cli.inventory import main; from ansible.cli.playbook import main' >/dev/null 2>&1; then
            _spa_venv_fail "spa_venv: Ansible cannot start with $(python -c 'import sys; print("Python %d.%d" % sys.version_info[:2])'). Rebuild with a supported interpreter, for example: spa venv --shared --rebuild --python python3.14 --yes"
        fi
        rm -rf "$_spa_venv_probe_tmp"
    fi

    # ansible-core ships no collection filters (e.g. json_query). Keep them beside
    # the venv so developer machines do not depend on ~/.ansible.
    if [[ $_spa_venv_rc -eq 0 ]] && command -v ansible-galaxy >/dev/null 2>&1 && [[ -f "${_spa_venv_home}/requirements.yml" ]]; then
        _spa_venv_collections="${SPA_COLLECTIONS_DIR:-$(dirname "$_spa_venv_dir")/.collections}"
        mkdir -p "$_spa_venv_collections"
        export ANSIBLE_COLLECTIONS_PATH="$_spa_venv_collections"
        _spa_venv_need_collections=false
        while read -r _spa_venv_name; do
            [[ -n "$_spa_venv_name" ]] || continue
            # community.general -> community/general
            _spa_venv_ns="${_spa_venv_name%%.*}/${_spa_venv_name#*.}"
            if [[ ! -d "${_spa_venv_collections}/ansible_collections/${_spa_venv_ns}" ]]; then
                _spa_venv_need_collections=true
            fi
        done < <(awk '/^[[:space:]]*-[[:space:]]*name:/ {print $3}' "${_spa_venv_home}/requirements.yml")
        if [[ "$_spa_venv_upgrade" == true ]]; then
            # --upgrade: bump every collection that has a newer Galaxy release.
            # Do not --force; that rewrites the same version instead of updating.
            _spa_venv_progress "Updating Ansible collections..."
            ansible-galaxy collection install --upgrade \
                -r "${_spa_venv_home}/requirements.yml" -p "$_spa_venv_collections"
        elif [[ "$_spa_venv_need_collections" == true ]]; then
            # --force: galaxy reports "nothing to do" when a collection exists in
            # ~/.ansible, which would leave ANSIBLE_COLLECTIONS_PATH empty here.
            _spa_venv_progress "Installing Ansible collections..."
            ansible-galaxy collection install --force \
                -r "${_spa_venv_home}/requirements.yml" -p "$_spa_venv_collections"
        else
            # .collections sits beside the venv, so it outlives a --rebuild. Say
            # so rather than skipping the step without a word.
            _spa_venv_progress "Ansible collections already installed"
        fi
        unset _spa_venv_collections _spa_venv_name _spa_venv_ns _spa_venv_need_collections
    fi
fi

if [[ "$_spa_venv_mode" == "create" && $_spa_venv_rc -eq 0 ]]; then
    echo "Virtual environment ready: ${_spa_venv_dir}"
fi

if [[ -f "${_spa_venv_dir}/bin/activate" ]]; then
    SPA_VENV_DIR="$_spa_venv_dir"
    export SPA_VENV_DIR
else
    # Never pin SPA_VENV_DIR to a venv we could not activate: spa resolves every
    # tool against it and would fail instead of falling back to SPA_HOME/.venv.
    unset SPA_VENV_DIR
fi

_spa_venv_exit=$_spa_venv_rc
unset -f _spa_venv_usage _spa_venv_fail _spa_venv_progress \
    _spa_venv_python_band _spa_venv_choose_python
unset _spa_venv_self _spa_venv_bin_dir _spa_venv_home _spa_venv_env \
    _spa_venv_python _spa_venv_python_explicit _spa_venv_mode _spa_venv_create _spa_venv_install \
    _spa_venv_reinstall _spa_venv_upgrade _spa_venv_rebuild \
    _spa_venv_reqs _spa_venv_pkgs _spa_venv_req _spa_venv_fresh \
    _spa_venv_dir _spa_venv_rc _spa_venv_probe_tmp

if [[ "$_spa_venv_sourced" == true ]]; then
    unset _spa_venv_sourced
    return $_spa_venv_exit 2>/dev/null || true
else
    unset _spa_venv_sourced
    exit $_spa_venv_exit
fi
