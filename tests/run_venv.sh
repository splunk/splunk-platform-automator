#!/bin/bash
# ==============================================================================
# Common venv setup for test run scripts
# ==============================================================================
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
SCRIPT_DIR="${SCRIPT_DIR:-$_venv_script_dir}"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$SCRIPT_DIR")}"

VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating test runner virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
else
    source "$VENV_DIR/bin/activate"
fi

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
if [[ ${#_run_venv_pkgs[@]} -gt 0 ]]; then
    pip install -q "${_run_venv_pkgs[@]}"
fi
unset _arg _run_venv_pkgs

cd "$PROJECT_ROOT"
