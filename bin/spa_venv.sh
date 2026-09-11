#!/usr/bin/env bash
# ==============================================================================
# Shared Python virtualenv for Splunk Platform Automator.
# One implementation for the framework, env dirs, and the test runners.
# ==============================================================================
# Usage:
#   source bin/spa_venv.sh                  # activate (create when missing)
#   source bin/spa_venv.sh --no-create      # activate only if it already exists
#   ./bin/spa_venv.sh --create              # create/update, then exit
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
_spa_venv_mode="activate"
_spa_venv_create=true
_spa_venv_install=true
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
    # A directory without bin/activate is a half-created venv (interrupted or
    # failed install); rebuild it rather than sourcing something broken.
    if [[ -d "$_spa_venv_dir" && ! -f "${_spa_venv_dir}/bin/activate" ]]; then
        if [[ "$_spa_venv_create" == true ]]; then
            echo "spa_venv: incomplete venv at ${_spa_venv_dir}, recreating"
            rm -rf "$_spa_venv_dir"
        fi
    fi

    if [[ ! -d "$_spa_venv_dir" ]]; then
        if [[ "$_spa_venv_create" != true ]]; then
            echo "spa_venv: no venv at ${_spa_venv_dir} (create it with: ${_spa_venv_bin_dir}/spa_venv.sh --create)" >&2
            _spa_venv_mode="done"
        elif ! command -v "$_spa_venv_python" >/dev/null 2>&1; then
            _spa_venv_fail "spa_venv: interpreter not found: ${_spa_venv_python}"
        else
            echo "Creating virtual environment: ${_spa_venv_dir}"
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
    if [[ "${_spa_venv_fresh:-false}" == true ]]; then
        pip install --upgrade pip
        for _spa_venv_req in "${_spa_venv_reqs[@]}"; do
            [[ -f "$_spa_venv_req" ]] || continue
            pip install -r "$_spa_venv_req"
        done
    fi
    if [[ ${#_spa_venv_pkgs[@]} -gt 0 ]]; then
        pip install -q "${_spa_venv_pkgs[@]}"
    fi

    # ansible-core ships no collection filters (e.g. json_query). Keep them beside
    # the venv so developer machines do not depend on ~/.ansible.
    if command -v ansible-galaxy >/dev/null 2>&1 && [[ -f "${_spa_venv_home}/requirements.yml" ]]; then
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
        if [[ "$_spa_venv_need_collections" == true ]]; then
            # --force: galaxy reports "nothing to do" when a collection exists in
            # ~/.ansible, which would leave ANSIBLE_COLLECTIONS_PATH empty here.
            echo "Installing Ansible collections from requirements.yml..."
            ansible-galaxy collection install --force \
                -r "${_spa_venv_home}/requirements.yml" -p "$_spa_venv_collections"
        fi
        unset _spa_venv_collections _spa_venv_name _spa_venv_ns _spa_venv_need_collections
    fi
fi

if [[ "$_spa_venv_mode" == "create" && $_spa_venv_rc -eq 0 ]]; then
    echo "Virtual environment ready: ${_spa_venv_dir}"
fi

SPA_VENV_DIR="$_spa_venv_dir"
export SPA_VENV_DIR

_spa_venv_exit=$_spa_venv_rc
unset -f _spa_venv_usage _spa_venv_fail
unset _spa_venv_self _spa_venv_bin_dir _spa_venv_home _spa_venv_env \
    _spa_venv_python _spa_venv_mode _spa_venv_create _spa_venv_install \
    _spa_venv_reqs _spa_venv_pkgs _spa_venv_req _spa_venv_fresh \
    _spa_venv_dir _spa_venv_rc

if [[ "$_spa_venv_sourced" == true ]]; then
    unset _spa_venv_sourced
    return $_spa_venv_exit 2>/dev/null || true
else
    unset _spa_venv_sourced
    exit $_spa_venv_exit
fi
