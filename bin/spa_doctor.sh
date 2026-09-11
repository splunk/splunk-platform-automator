#!/usr/bin/env bash
# ==============================================================================
# Check host prerequisites for Splunk Platform Automator (not pip packages).
# Ansible, Pydantic, and collections come from bin/spa_venv.sh — not Homebrew.
# ==============================================================================
# Usage:
#   ./bin/spa_doctor.sh
#   ./bin/spa_doctor.sh --lab ~/labs/my-lab
#   ./bin/spa_doctor.sh --aws              # require terraform (AWS labs)
#   ./bin/spa_doctor.sh --json
#
# Exit 0 when all required checks pass; 1 when something required is missing.
# Warnings (direnv, Software/) do not fail unless --strict.
# Terraform is required only for AWS labs; Vagrant only for VirtualBox labs.
# ==============================================================================

set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPA_HOME="$(cd "${SPA_HOME:-$BIN_DIR/..}" && pwd)"
LAB_DIR=""
REQUIRE_AWS=false
REQUIRE_VBOX=false
STRICT=false
JSON=false
FIX_DIRENV=false

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

ERRORS=0
WARNS=0

usage() {
    cat <<'EOF'
Usage: spa_doctor.sh [options]

Host tools SPA expects outside the Python venv (bin/spa_venv.sh).

  --spa-home DIR   Framework checkout (default: parent of bin/)
  --lab DIR        Lab dir (Software sibling; AWS/VirtualBox inferred from config)
  --aws            Require Terraform (AWS provision/destroy)
  --virtualbox     Require Vagrant (VirtualBox labs)
  --strict         Exit 1 on warnings as well as errors
  --json           Machine-readable summary on stdout
  --fix-direnv     If direnv is installed, add the shell hook to your rc file
                   (~/.zshrc or ~/.bashrc) when it is missing. Does not install
                   direnv itself.
  -h, --help       This help
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --spa-home)
            [[ $# -ge 2 ]] || usage
            SPA_HOME="$(cd "$2" && pwd)"
            shift 2
            ;;
        --lab)
            [[ $# -ge 2 ]] || usage
            LAB_DIR="$(cd "$2" && pwd)"
            shift 2
            ;;
        --aws)
            REQUIRE_AWS=true
            shift
            ;;
        --virtualbox)
            REQUIRE_VBOX=true
            shift
            ;;
        --strict)
            STRICT=true
            shift
            ;;
        --json)
            JSON=true
            shift
            ;;
        --fix-direnv)
            FIX_DIRENV=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

_brew_hint() {
    local pkg="$1"
    if command -v brew >/dev/null 2>&1; then
        echo "brew install ${pkg}"
    else
        echo "install ${pkg} with your OS package manager"
    fi
}

_record() {
    local level="$1" id="$2" msg="$3" fix="${4:-}"
    case "$level" in
        ok)    _results_ok+=("$id|$msg") ;;
        warn)  _results_warn+=("$id|$msg|$fix"); WARNS=$((WARNS + 1)) ;;
        error) _results_err+=("$id|$msg|$fix"); ERRORS=$((ERRORS + 1)) ;;
    esac
}

_direnv_hook_line() {
    case "${SHELL##*/}" in
        bash) echo 'eval "$(direnv hook bash)"' ;;
        fish) echo 'direnv hook fish | source' ;;
        *)    echo 'eval "$(direnv hook zsh)"' ;;
    esac
}

_direnv_target_rc() {
    case "${SHELL##*/}" in
        bash)
            if [[ -f "${HOME}/.bashrc" ]]; then
                echo "${HOME}/.bashrc"
            else
                echo "${HOME}/.bash_profile"
            fi
            ;;
        fish) echo "${HOME}/.config/fish/config.fish" ;;
        *)    echo "${HOME}/.zshrc" ;;
    esac
}

_direnv_hook_in_rc() {
    # Follow source / . from the usual rc files so a hook in a nested zshrc still counts.
    HOME="${HOME}" python3 - <<'PY'
import os, re, sys

home = os.environ.get("HOME", "")
roots = [
    os.path.join(home, ".zshrc"),
    os.path.join(home, ".zprofile"),
    os.path.join(home, ".zshenv"),
    os.path.join(home, ".bashrc"),
    os.path.join(home, ".bash_profile"),
    os.path.join(home, ".config", "fish", "config.fish"),
]
source_re = re.compile(r"^\s*(?:source|\.)\s+(.+)$", re.MULTILINE)
hook_re = re.compile(r"direnv\s+hook")
seen = set()


def first_path(rest: str) -> str:
    rest = rest.split("#", 1)[0].strip()
    if not rest:
        return ""
    if rest[0] in "'\"":
        q = rest[0]
        end = rest.find(q, 1)
        return rest[1:end] if end > 0 else rest[1:]
    return rest.split()[0]


def expand(path: str) -> str:
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)
    return os.path.abspath(path)


def scan(path: str, depth: int = 0) -> bool:
    if depth > 20:
        return False
    try:
        path = expand(path)
    except Exception:
        return False
    if path in seen or not os.path.isfile(path):
        return False
    seen.add(path)
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    if hook_re.search(text):
        return True
    for match in source_re.finditer(text):
        nxt = first_path(match.group(1))
        if nxt and scan(nxt, depth + 1):
            return True
    return False


sys.exit(0 if any(os.path.isfile(p) and scan(p) for p in roots) else 1)
PY
}

_direnv_apply_hook() {
    local rc line
    if _direnv_hook_in_rc; then
        return 0
    fi
    rc="$(_direnv_target_rc)"
    line="$(_direnv_hook_line)"
    mkdir -p "$(dirname "$rc")"
    touch "$rc"
    {
        echo ""
        echo "# Splunk Platform Automator: load lab .envrc when you cd into a lab"
        echo "$line"
    } >> "$rc"
    echo "Added direnv to ${rc}."
    echo "Close this terminal and open a new one, then open your lab folder again."
}

_results_ok=()
_results_warn=()
_results_err=()

if [[ -n "$LAB_DIR" && -f "${LAB_DIR}/config/splunk_config.yml" ]]; then
    _cfg="${LAB_DIR}/config/splunk_config.yml"
    if [[ "$REQUIRE_AWS" != true ]] \
        && grep -qE '^terraform:' "$_cfg" 2>/dev/null \
        && grep -qE '^[[:space:]]+aws:' "$_cfg" 2>/dev/null; then
        REQUIRE_AWS=true
    fi
    # Top-level virtualbox: (VirtualBox/Vagrant labs). AWS examples omit this key.
    if [[ "$REQUIRE_VBOX" != true ]] && grep -qE '^virtualbox:' "$_cfg" 2>/dev/null; then
        REQUIRE_VBOX=true
    fi
fi

# --- Required: Python for spa_venv ---
if command -v python3 >/dev/null 2>&1; then
    _py_ver="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo unknown)"
    if python3 -c 'import venv' 2>/dev/null; then
        _record ok python "python3 (${_py_ver}) with venv module"
    else
        _record error python "python3 found but venv module missing" "$(_brew_hint python3)"
    fi
else
    _record error python "python3 not on PATH" "$(_brew_hint python3)"
fi

# --- Shared venv (created on first spa_venv.sh use) ---
_venv="${SPA_HOME}/.venv"
if [[ -f "${_venv}/bin/activate" ]]; then
    _record ok spa_venv "shared venv at ${_venv}"
else
    _record warn spa_venv "shared venv not created yet" "${SPA_HOME}/bin/spa_venv.sh --create"
fi

# --- bin/ on PATH: spash must come from this SPA_HOME, not another clone ---
_spash_on_path="$(command -v spash 2>/dev/null || true)"
if [[ -z "$_spash_on_path" ]]; then
    _record warn spash "spash is not on PATH" \
        "cd the lab (direnv), or run ${SPA_HOME}/bin/spash directly"
elif [[ "$(cd "$(dirname "$_spash_on_path")" && pwd)" != "${SPA_HOME}/bin" ]]; then
    _record warn spash \
        "spash on PATH is ${_spash_on_path}, not ${SPA_HOME}/bin/spash (another checkout wins)" \
        "re-run init_spa_dir.sh so .envrc puts \$SPA_HOME/bin first, then reload the folder (direnv reload)"
else
    _record ok spash "spash resolves to ${SPA_HOME}/bin/spash"
fi

# --- Terraform (AWS labs only) ---
if [[ "$REQUIRE_AWS" == true ]]; then
    if command -v terraform >/dev/null 2>&1; then
        _tf_ver="$(terraform version -json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("terraform_version","?"))' 2>/dev/null || terraform version | head -1)"
        _record ok terraform "terraform (${_tf_ver})"
    else
        _record error terraform "terraform required for AWS (not on PATH)" "$(_brew_hint terraform)"
    fi
fi

# --- direnv (optional; needed for automatic env when you open a lab folder) ---
if [[ "$FIX_DIRENV" == true ]]; then
    _direnv_apply_hook
fi
if command -v direnv >/dev/null 2>&1; then
    if _direnv_hook_in_rc; then
        if [[ -n "${DIRENV_DIR:-}" ]]; then
            _record ok direnv "direnv is installed and this folder's environment is loaded"
        else
            _record ok direnv "direnv is installed and set up in your shell startup file"
        fi
    else
        _record warn direnv \
            "direnv is installed, but your shell does not load it yet — opening a lab folder will not set up Ansible until you do this once" \
            "${SPA_HOME}/bin/spa_doctor.sh --fix-direnv  (then close the terminal and open a new one)"
    fi
else
    _record warn direnv \
        "direnv is not installed — you would have to set up the lab by hand every time" \
        "$(_brew_hint direnv); then ${SPA_HOME}/bin/spa_doctor.sh --fix-direnv"
fi

# --- Software directory ---
_software=""
if [[ -n "$LAB_DIR" ]]; then
    for candidate in "${LAB_DIR}/../Software" "${SPA_HOME}/../Software" "${SPA_HOME}/Software"; do
        if [[ -d "$candidate" ]]; then
            _software="$(cd "$candidate" && pwd)"
            break
        fi
    done
fi
if [[ -n "$_software" ]]; then
    _record ok software "Software at ${_software}"
else
    _record warn software "no Software/ directory (installers and baseconfig apps)" \
        "sibling of lab or SPA_HOME: ../Software"
fi

# --- Vagrant (VirtualBox labs only) ---
if [[ "$REQUIRE_VBOX" == true ]]; then
    if command -v vagrant >/dev/null 2>&1; then
        _record ok vagrant "vagrant ($(vagrant --version 2>/dev/null | head -1))"
    else
        _record error vagrant "vagrant required for VirtualBox labs (not on PATH)" "$(_brew_hint vagrant)"
    fi
fi

# --- Homebrew ansible/pydantic: informational only ---
if command -v brew >/dev/null 2>&1; then
    _record ok brew "Homebrew available (optional; SPA uses spa_venv, not brew ansible)"
fi

if [[ "$JSON" == true ]]; then
    printf '{'
    printf '"errors":%s,' "$ERRORS"
    printf '"warnings":%s,' "$WARNS"
    printf '"checks":['
    _first=true
    for line in "${_results_ok[@]}"; do
        IFS='|' read -r id msg <<< "$line"
        [[ "$_first" == true ]] || printf ','
        _first=false
        printf '{"level":"ok","id":"%s","message":"%s"}' "$id" "$msg"
    done
    for line in "${_results_warn[@]}"; do
        IFS='|' read -r id msg fix <<< "$line"
        [[ "$_first" == true ]] || printf ','
        _first=false
        printf '{"level":"warn","id":"%s","message":"%s","fix":"%s"}' "$id" "$msg" "$fix"
    done
    for line in "${_results_err[@]}"; do
        IFS='|' read -r id msg fix <<< "$line"
        [[ "$_first" == true ]] || printf ','
        _first=false
        printf '{"level":"error","id":"%s","message":"%s","fix":"%s"}' "$id" "$msg" "$fix"
    done
    printf ']}\n'
else
    echo "SPA host prerequisites (SPA_HOME=${SPA_HOME})"
    echo
    for line in "${_results_ok[@]}"; do
        IFS='|' read -r id msg <<< "$line"
        echo -e "${GREEN}OK${NC}   ${msg}"
    done
    for line in "${_results_warn[@]}"; do
        IFS='|' read -r id msg fix <<< "$line"
        echo -e "${YELLOW}WARN${NC} ${msg}"
        echo "       → ${fix}"
    done
    for line in "${_results_err[@]}"; do
        IFS='|' read -r id msg fix <<< "$line"
        echo -e "${RED}FAIL${NC} ${msg}"
        echo "       → ${fix}"
    done
    echo
    if [[ $ERRORS -gt 0 ]]; then
        echo -e "${RED}${ERRORS} required check(s) failed.${NC}"
    elif [[ $WARNS -gt 0 ]]; then
        echo -e "${YELLOW}${WARNS} warning(s).${NC} Lab may still work; fix before deploy if they apply."
    else
        echo -e "${GREEN}All checks passed.${NC}"
    fi
fi

if [[ $ERRORS -gt 0 ]]; then
    exit 1
fi
if [[ "$STRICT" == true && $WARNS -gt 0 ]]; then
    exit 1
fi
exit 0
