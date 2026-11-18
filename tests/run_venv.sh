#!/bin/bash
# ==============================================================================
# Common venv setup for test run scripts
# ==============================================================================
# Thin wrapper around bin/spa_venv.sh. The tests keep their own venv
# (tests/.venv) so pytest dependencies never land in the venv a lab uses.
#
# Source this script from other run_*.sh scripts to create/activate tests/.venv
# and cd to project root. Optionally pass extra pip packages to install after
# activate (e.g. "pydantic>=2.0" or "ansible-core").
#
# Usage (from a script in tests/):
#   source "$(dirname "${BASH_SOURCE[0]}")/run_venv.sh"
#   source "$(dirname "${BASH_SOURCE[0]}")/run_venv.sh" "pydantic>=2.0"
#   source "$(dirname "${BASH_SOURCE[0]}")/run_venv.sh" "pydantic>=2.0" ansible-core
#
# Prerequisites: set -e and SCRIPT_DIR/PROJECT_ROOT may be set by caller;
# if not set, they are derived from this script's location.
# ==============================================================================

# Resolve tests dir (where run_venv.sh lives) and project root
_venv_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_venv_project_root="$(dirname "$_venv_script_dir")"
SCRIPT_DIR="${SCRIPT_DIR:-$_venv_script_dir}"
PROJECT_ROOT="${PROJECT_ROOT:-$_venv_project_root}"

VENV_DIR="${VENV_DIR:-$_venv_script_dir/.venv}"

mkdir -p "${ANSIBLE_LOCAL_TEMP:-$_venv_script_dir/.ansible_tmp}"

# Optional: install extra packages (only when explicitly passed to source command).
# When sourced, we inherit the caller's $@ (e.g. pytest -n 2 -v); only run pip for
# args that look like package specs (contain a letter; exclude bare numbers like -n 2).
_run_venv_pkgs=()
for _arg in "$@"; do
    [[ "$_arg" == -* ]] && continue
    # Exclude bare numbers (e.g. -n 2) and other non-package args
    [[ "$_arg" =~ ^[0-9]+$ ]] && continue
    [[ "$_arg" == *[a-zA-Z]* ]] && _run_venv_pkgs+=("$_arg")
done

# shellcheck disable=SC1090
source "${_venv_project_root}/bin/spa_venv.sh" \
    --dir "$VENV_DIR" \
    --requirements "${_venv_script_dir}/requirements.txt" \
    "${_run_venv_pkgs[@]}"

unset _arg _run_venv_pkgs _venv_script_dir _venv_project_root

cd "$PROJECT_ROOT"
