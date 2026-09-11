#!/usr/bin/env bash
# ==============================================================================
# Scaffold or migrate a lab directory against one SPA_HOME clone (Distribution M1).
# Does not copy ansible/. spa init (M2) will wrap this script.
# ==============================================================================
# Usage:
#   ./bin/init_spa_dir.sh [--example NAME] [--force] LAB_DIR
#   ./bin/init_spa_dir.sh [--from DIR] [--keep-source] LAB_DIR
#   ./bin/init_spa_dir.sh --venv [--python PATH] LAB_DIR
#
# Default example: single_node.yml. If SPA_HOME (or --from) already has
# config/splunk_config.yml, that existing env is migrated instead.
# ==============================================================================

set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SPA_HOME="$(cd "$BIN_DIR/.." && pwd)"
SPA_HOME="${SPA_HOME:-$DEFAULT_SPA_HOME}"

EXAMPLE="single_node.yml"
EXAMPLE_SET=false
FORCE=false
KEEP_SOURCE=false
FROM_DIR=""
MIGRATE_SET=false
LAB_DIR=""
LAB_VENV=false
LAB_PYTHON=""
WRITE_ENVRC=true
SKIP_DOCTOR=false

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
    cat <<'EOF'
Usage: init_spa_dir.sh [options] LAB_DIR

Scaffold a lab directory (config/, inventory/, terraform/aws/, .spa.yml).
Never copies ansible/. Refuses to overwrite an existing M1 lab unless --force.

If SPA_HOME (or --from) already has config/splunk_config.yml, the existing
environment is migrated: config, inventory, and Terraform state are kept so a
running deployment stays manageable from the new lab dir.

  --example NAME   Fresh lab from examples/ (default: single_node.yml).
                   Skips auto-migrate. AWS C1: cm_2idxc_sh_uf_aws.yml
  --from DIR       Source of an existing env (default: SPA_HOME)
  --migrate        Require migrate (fail if the source has no config)
  --keep-source    Copy lab state; do not remove it from the source
  --force          Overwrite config/.spa.yml in an existing lab
  --venv           Create a lab-local .venv (pin Python/Ansible for this lab).
                   Default is the shared venv in the clone (SPA_HOME).
                   Init creates the chosen venv when it is missing.
  --python PATH    Interpreter for --venv (implies --venv)
  --no-envrc       Do not write .envrc (direnv auto-activation)
  --skip-doctor    Skip bin/spa_doctor.sh host prerequisite check
  LAB_DIR          Target directory (must not be SPA_HOME)
EOF
    exit 1
}

has_lab_config() {
    [[ -f "${1}/config/splunk_config.yml" ]]
}

is_m1_lab() {
    [[ -f "${1}/.spa.yml" ]]
}

is_old_clone_tree() {
    [[ -d "${1}/ansible" && -f "${1}/config/splunk_config.yml" ]]
}

transfer_path() {
    local src="$1" dest="$2"
    if [[ ! -e "$src" && ! -L "$src" ]]; then
        return 0
    fi
    mkdir -p "$(dirname "$dest")"
    if [[ -d "$src" && ! -L "$src" ]]; then
        mkdir -p "$dest"
        cp -a "$src"/. "$dest"/
    else
        cp -a "$src" "$dest"
    fi
    if [[ "$KEEP_SOURCE" != true ]]; then
        rm -rf "$src"
    fi
}

write_spa_yml() {
    local dest="$1"
    local software_dir=""
    local apps_dir=""
    for candidate in "${dest}/../Software" "${SPA_HOME}/../Software" "${SPA_HOME}/Software"; do
        if [[ -d "$candidate" ]]; then
            software_dir="$(cd "$candidate" && pwd)"
            break
        fi
    done
    for candidate in "${dest}/../apps" "${SPA_HOME}/../apps" "${SPA_HOME}/apps"; do
        if [[ -d "$candidate" ]]; then
            apps_dir="$(cd "$candidate" && pwd)"
            break
        fi
    done
    {
        echo "# Splunk Platform Automator lab pointer (Distribution M1)."
        echo "# Framework stays in spa_home. Do not copy ansible/ into this directory."
        echo "spa_home: ${SPA_HOME}"
        if [[ -n "$software_dir" ]]; then
            echo "software_dir: ${software_dir}"
            echo "baseconfig_dir: ${software_dir}"
        fi
        if [[ -n "$apps_dir" ]]; then
            echo "apps_dir: ${apps_dir}"
        fi
    } > "${dest}/.spa.yml"
    SOFTWARE_DIR="$software_dir"
    APPS_DIR="$apps_dir"
}

print_shared_dirs() {
    if [[ -n "${SOFTWARE_DIR:-}" ]]; then
        echo "  Software:  ${SOFTWARE_DIR}"
        echo "  Baseconfig:${SOFTWARE_DIR}"
    else
        echo "  Software / baseconfig: not found (lab sibling, then SPA_HOME sibling)"
        echo "             Extract installers and PS baseconfig apps, or set"
        echo "             software_dir / baseconfig_dir in .spa.yml (or SPA_SOFTWARE_DIR / SPA_BASECONFIG_DIR)."
    fi
    if [[ -n "${APPS_DIR:-}" ]]; then
        echo "  Apps:      ${APPS_DIR}"
    else
        echo "  Apps:      not found (lab sibling ../apps, then \$SPA_HOME/apps)"
        echo "             Place local apps there, or set apps_dir in .spa.yml (or SPA_APPS_DIR)."
        echo "             Per-lab override: splunk_app_deployment.local_app_repo_path in splunk_config.yml."
    fi
}

link_terraform_modules() {
    local dest_tf="${1}/terraform/aws"
    local src_tf="${SPA_HOME}/terraform/aws"
    mkdir -p "$dest_tf"
    [[ -d "$src_tf" ]] || return 0
    local tf
    for tf in "$src_tf"/*.tf; do
        [[ -f "$tf" ]] || continue
        ln -sfn "$tf" "${dest_tf}/$(basename "$tf")"
    done
}

ensure_lab_dirs() {
    local dest="$1"
    mkdir -p "${dest}/config" "${dest}/inventory" "${dest}/terraform/aws" \
        "${dest}/saved_base_config_apps"
    if [[ ! -e "${dest}/inventory/hosts" ]]; then
        : > "${dest}/inventory/hosts"
    fi
}

migrate_lab_state() {
    local src="$1" dest="$2"
    ensure_lab_dirs "$dest"

    if [[ -d "${src}/config" ]]; then
        local item
        for item in "${src}/config"/* "${src}/config"/.[!.]*; do
            [[ -e "$item" || -L "$item" ]] || continue
            transfer_path "$item" "${dest}/config/$(basename "$item")"
        done
        if [[ "$KEEP_SOURCE" != true ]]; then
            rmdir "${src}/config" 2>/dev/null || true
        fi
    fi

    if [[ -d "${src}/inventory" ]]; then
        local inv
        for inv in "${src}/inventory"/* "${src}/inventory"/.[!.]*; do
            [[ -e "$inv" || -L "$inv" ]] || continue
            transfer_path "$inv" "${dest}/inventory/$(basename "$inv")"
        done
        if [[ "$KEEP_SOURCE" != true ]]; then
            rmdir "${src}/inventory" 2>/dev/null || true
        fi
    fi

    if [[ -d "${src}/terraform/aws" ]]; then
        local name
        for name in terraform.tfvars terraform.tfstate terraform.tfstate.backup \
            tfplan .terraform.lock.hcl .terraform; do
            transfer_path "${src}/terraform/aws/${name}" "${dest}/terraform/aws/${name}"
        done
    fi

    for extra in .vault_pass .vault_pass.txt; do
        if [[ -f "${src}/${extra}" ]]; then
            transfer_path "${src}/${extra}" "${dest}/${extra}"
        fi
    done

    link_terraform_modules "$dest"
    write_spa_yml "$dest"
}

strip_framework_from_lab() {
    local dest="$1"
    local name
    for name in ansible bin tests skills examples docs defaults template scripts \
        .github .cursor .agent .git \
        Vagrantfile ansible.cfg requirements.txt requirements.yml \
        CHANGELOG.md README.md ROADMAP.md AGENTS.md RELEASE.md LICENSE \
        CONTRIBUTING.md SECURITY.md .gitattributes .gitmodules; do
        rm -rf "${dest}/${name}"
    done
    local tf
    if [[ -d "${dest}/terraform/aws" ]]; then
        for tf in "${dest}/terraform/aws"/*.tf; do
            [[ -e "$tf" || -L "$tf" ]] || continue
            if [[ -L "$tf" ]]; then
                continue
            fi
            rm -f "$tf"
        done
        rm -f "${dest}/terraform/aws/README.md"
    fi
    link_terraform_modules "$dest"
}

write_envrc() {
    local dest="$1"
    [[ "$WRITE_ENVRC" == true ]] || return 0
    cat > "${dest}/.envrc" <<EOF
# Splunk Platform Automator lab environment (direnv). Enable with: direnv allow
# Activates the venv (lab .venv when present, else SPA_HOME/.venv) and exports
# SPA_HOME / SPA_LAB_DIR / ANSIBLE_* so ansible-playbook uses this lab.
export SPA_HOME="${SPA_HOME}"
export SPA_LAB_DIR="\$(pwd)"
# A value inherited from another lab's shell must not win over this directory.
unset SPLUNK_CONFIG_FILE
# A lab has no bin/ of its own, so put the framework's on PATH for spash and
# friends. Prepending also keeps another checkout on PATH from winning.
if declare -f PATH_add >/dev/null 2>&1; then
    PATH_add "\${SPA_HOME}/bin"
else
    export PATH="\${SPA_HOME}/bin:\${PATH}"
fi
source "\${SPA_HOME}/bin/spa_venv.sh" --no-create --lab "\${SPA_LAB_DIR}"
eval "\$("\${SPA_HOME}/bin/spa_env.sh" --start-dir "\${SPA_LAB_DIR}")"
EOF
}

# Shared clone venv by default; --venv uses LAB/.venv. Create when missing.
ensure_venv() {
    local dest="$1"
    local venv_dir="${DEFAULT_SPA_HOME}/.venv"
    local extra=()
    if [[ "$LAB_VENV" == true ]]; then
        venv_dir="${dest}/.venv"
        if [[ -n "$LAB_PYTHON" ]]; then
            extra=(--python "$LAB_PYTHON")
        fi
    fi
    if [[ -f "${venv_dir}/bin/activate" ]]; then
        echo "  venv:      ${venv_dir} (existing)"
        return 0
    fi
    echo -e "${GREEN}Creating Python venv: ${venv_dir}${NC}"
    "${BIN_DIR}/spa_venv.sh" --create --dir "$venv_dir" "${extra[@]}"
}

allow_direnv() {
    local dest="$1"
    [[ "$WRITE_ENVRC" == true ]] || return 0
    if command -v direnv >/dev/null 2>&1; then
        if (cd "$dest" && direnv allow >/dev/null 2>&1); then
            echo -e "${GREEN}direnv: approved ${dest}/.envrc (cd into the lab to load venv + SPA_*)${NC}"
            DIRENV_ALLOWED=true
        else
            echo -e "${YELLOW}direnv: could not approve .envrc (run: cd ${dest} && direnv allow)${NC}"
        fi
    fi
}

run_spa_doctor() {
    local dest="$1"
    [[ "$SKIP_DOCTOR" == true ]] && return 0
    local doctor="${BIN_DIR}/spa_doctor.sh"
    [[ -x "$doctor" ]] || doctor="${SPA_HOME}/bin/spa_doctor.sh"
    [[ -x "$doctor" ]] || return 0
    local extra=()
    # Interactive terminals: add the direnv line to ~/.zshrc (or bashrc) if missing.
    # Non-interactive (tests, CI) skip so we never edit the developer's rc file.
    if [[ -t 1 ]]; then
        extra+=(--fix-direnv)
    fi
    echo
    if ! "$doctor" --spa-home "$SPA_HOME" --lab "$dest" "${extra[@]}"; then
        echo -e "${RED}Host prerequisite check failed. Fix the items above before provision/deploy.${NC}" >&2
        echo "  ${doctor} --lab ${dest}" >&2
        exit 1
    fi
}

post_lab_setup() {
    local dest="$1" mode="$2"
    allow_direnv "$dest"
    run_spa_doctor "$dest"
    print_next_steps "$dest" "$mode"
}

print_next_steps() {
    local dest="$1" mode="$2"
    echo
    if [[ "$mode" == "fresh" ]]; then
        echo "Your lab folder is ready: ${dest}"
    else
        echo "Your lab was moved to ${dest} (not the clone)."
        echo "Do not provision or destroy from the old clone path — Terraform state lives here."
    fi
    echo
    echo "What to do next:"
    echo
    if command -v direnv >/dev/null 2>&1 && [[ "$WRITE_ENVRC" == true ]]; then
        echo "  1. Close this terminal and open a new one (only needed once, after direnv setup)."
        echo "  2. Type:  cd ${dest}"
        echo "     You should see a short message that the lab environment loaded."
        echo "  3. Then:  ${SPA_HOME}/bin/validate_splunk_config.sh"
        if [[ "${DIRENV_ALLOWED:-false}" != true ]]; then
            echo "     If you see 'blocked', type:  direnv allow"
        fi
    else
        echo "  1. Type these two lines (every new terminal), then validate:"
        echo "       source ${SPA_HOME}/bin/spa_venv.sh --lab ${dest}"
        echo "       eval \"\$(${SPA_HOME}/bin/spa_env.sh --start-dir ${dest})\""
        echo "       ${SPA_HOME}/bin/validate_splunk_config.sh"
        echo "  To load the lab automatically when you open the folder, install direnv once:"
        echo "       $(_brew_hint_init direnv)"
        echo "       ${SPA_HOME}/bin/spa_doctor.sh --fix-direnv"
        echo "     Then close the terminal, open a new one, and:  cd ${dest}"
    fi
    echo
    echo "ansible-playbook uses this lab's config (not the clone's)."
}

_brew_hint_init() {
    if command -v brew >/dev/null 2>&1; then
        echo "brew install $1"
    else
        echo "install $1 with your package manager"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --example)
            [[ $# -ge 2 ]] || usage
            EXAMPLE="$2"
            EXAMPLE_SET=true
            shift 2
            ;;
        --from)
            [[ $# -ge 2 ]] || usage
            FROM_DIR="$2"
            MIGRATE_SET=true
            shift 2
            ;;
        --migrate)
            MIGRATE_SET=true
            shift
            ;;
        --keep-source)
            KEEP_SOURCE=true
            shift
            ;;
        --venv)
            LAB_VENV=true
            shift
            ;;
        --python)
            [[ $# -ge 2 ]] || usage
            LAB_PYTHON="$2"
            LAB_VENV=true
            shift 2
            ;;
        --no-envrc)
            WRITE_ENVRC=false
            shift
            ;;
        --skip-doctor)
            SKIP_DOCTOR=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}" >&2
            usage
            ;;
        *)
            if [[ -n "$LAB_DIR" ]]; then
                echo -e "${RED}Unexpected argument: $1${NC}" >&2
                usage
            fi
            LAB_DIR="$1"
            shift
            ;;
    esac
done

[[ -n "$LAB_DIR" ]] || usage

if [[ "$EXAMPLE_SET" == true && "$MIGRATE_SET" == true ]]; then
    echo -e "${RED}Use either --example or --from/--migrate, not both.${NC}" >&2
    exit 1
fi

EXAMPLE="${EXAMPLE#examples/}"
if [[ "$EXAMPLE" != *.yml && "$EXAMPLE" != *.yaml ]]; then
    EXAMPLE="${EXAMPLE}.yml"
fi

if [[ "$LAB_DIR" != /* ]]; then
    LAB_DIR="$(pwd)/${LAB_DIR}"
fi
mkdir -p "$LAB_DIR"
LAB_DIR="$(cd "$LAB_DIR" && pwd)"
SPA_HOME="$(cd "$SPA_HOME" && pwd)"

if [[ -n "$FROM_DIR" ]]; then
    if [[ "$FROM_DIR" != /* ]]; then
        FROM_DIR="$(pwd)/${FROM_DIR}"
    fi
    if [[ ! -d "$FROM_DIR" ]]; then
        echo -e "${RED}--from directory not found: ${FROM_DIR}${NC}" >&2
        exit 1
    fi
    FROM_DIR="$(cd "$FROM_DIR" && pwd)"
fi

SOURCE="${FROM_DIR:-$SPA_HOME}"

if [[ "$LAB_DIR" == "$SPA_HOME" ]]; then
    echo -e "${RED}Refusing to scaffold into SPA_HOME (${SPA_HOME}).${NC}" >&2
    echo "This checkout is the framework. Pick another directory for the lab," >&2
    echo "or keep using config/splunk_config.yml here (clone-equal)." >&2
    exit 1
fi

if [[ "$SOURCE" == "$LAB_DIR" ]]; then
    echo -e "${RED}Source and LAB_DIR are the same path (${LAB_DIR}).${NC}" >&2
    echo "Pick a new lab directory, or run from the framework clone with --from pointing at the old env." >&2
    exit 1
fi

CONFIG_DEST="${LAB_DIR}/config/splunk_config.yml"
SPA_YML_DEST="${LAB_DIR}/.spa.yml"
SOFTWARE_DIR=""
APPS_DIR=""

if [[ "$FORCE" != true ]] && is_m1_lab "$LAB_DIR"; then
    echo -e "${RED}Lab already exists (${LAB_DIR}). Use --force to overwrite config/.spa.yml.${NC}" >&2
    exit 1
fi

# Dest is an old mixed clone (ansible/ + config) and we are not pulling from elsewhere.
if [[ "$EXAMPLE_SET" != true && -z "$FROM_DIR" ]] && is_old_clone_tree "$LAB_DIR"; then
    echo -e "${GREEN}Detected an existing clone-style env in ${LAB_DIR}${NC}"
    echo "Keeping config, inventory, and Terraform state; removing framework files."
    strip_framework_from_lab "$LAB_DIR"
    ensure_lab_dirs "$LAB_DIR"
    write_spa_yml "$LAB_DIR"
    write_envrc "$LAB_DIR"
    ensure_venv "$LAB_DIR"
    echo -e "${GREEN}Converted to a lab dir at ${LAB_DIR}${NC}"
    echo "  SPA_HOME:  ${SPA_HOME}"
    echo "  config:    ${CONFIG_DEST}"
    echo "  .spa.yml:  ${SPA_YML_DEST}"
    print_shared_dirs
    if [[ -d "${LAB_DIR}/.vagrant" ]]; then
        echo -e "${YELLOW}  Note: .vagrant/ is still here; VirtualBox VMs stay bound to this path.${NC}"
    fi
    post_lab_setup "$LAB_DIR" migrate
    exit 0
fi

WANT_MIGRATE=false
if [[ "$MIGRATE_SET" == true ]]; then
    WANT_MIGRATE=true
elif [[ "$EXAMPLE_SET" != true ]] && has_lab_config "$SOURCE"; then
    WANT_MIGRATE=true
fi

if [[ "$WANT_MIGRATE" == true ]]; then
    if ! has_lab_config "$SOURCE"; then
        echo -e "${RED}No config/splunk_config.yml in ${SOURCE}. Nothing to migrate.${NC}" >&2
        exit 1
    fi
    if [[ "$FORCE" != true ]] && has_lab_config "$LAB_DIR"; then
        echo -e "${RED}Lab already has a config (${CONFIG_DEST}). Use --force to replace it from the source.${NC}" >&2
        exit 1
    fi
    echo -e "${GREEN}Migrating existing env from ${SOURCE}${NC}"
    migrate_lab_state "$SOURCE" "$LAB_DIR"
    write_envrc "$LAB_DIR"
    ensure_venv "$LAB_DIR"
    echo -e "${GREEN}Lab migrated to ${LAB_DIR}${NC}"
    echo "  SPA_HOME:  ${SPA_HOME}"
    echo "  source:    ${SOURCE}"
    echo "  config:    ${CONFIG_DEST}"
    echo "  .spa.yml:  ${SPA_YML_DEST}"
    if [[ "$KEEP_SOURCE" == true ]]; then
        echo "  source files: kept (--keep-source)"
    else
        echo "  source files: moved (clone no longer holds lab state)"
    fi
    print_shared_dirs
    if [[ -d "${SOURCE}/.vagrant" ]]; then
        echo -e "${YELLOW}  Note: .vagrant/ was left in the source (VirtualBox is path-bound).${NC}"
    fi
    post_lab_setup "$LAB_DIR" migrate
    exit 0
fi

SOURCE_EXAMPLE="${SPA_HOME}/examples/${EXAMPLE}"
if [[ ! -f "$SOURCE_EXAMPLE" ]]; then
    echo -e "${RED}Example not found: ${SOURCE_EXAMPLE}${NC}" >&2
    exit 1
fi

if [[ "$FORCE" != true ]]; then
    if [[ -e "$CONFIG_DEST" || -e "$SPA_YML_DEST" ]]; then
        echo -e "${RED}Lab already exists (${LAB_DIR}). Use --force to overwrite config/.spa.yml.${NC}" >&2
        exit 1
    fi
fi

ensure_lab_dirs "$LAB_DIR"
cp "$SOURCE_EXAMPLE" "$CONFIG_DEST"
write_spa_yml "$LAB_DIR"
write_envrc "$LAB_DIR"
ensure_venv "$LAB_DIR"

echo -e "${GREEN}Lab scaffolded at ${LAB_DIR}${NC}"
echo "  SPA_HOME:  ${SPA_HOME}"
echo "  example:   ${EXAMPLE}"
echo "  config:    ${CONFIG_DEST}"
echo "  .spa.yml:  ${SPA_YML_DEST}"
print_shared_dirs
post_lab_setup "$LAB_DIR" fresh
