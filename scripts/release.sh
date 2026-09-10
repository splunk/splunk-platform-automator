#!/usr/bin/env bash
# Release helper: pre-checks, version bump, optional GitHub Release.
# Usage:
#   ./scripts/release.sh --check
#   ./scripts/release.sh patch|minor|major [--push] [--yes]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION_FILE="$ROOT/VERSION"
CHANGELOG="$ROOT/CHANGELOG.md"

GIT_REMOTE="origin"
GIT_BRANCH="master"
FLAG_PUSH=false
FLAG_YES=false
FLAG_CHECK=false
BUMP_TYPE=""

usage() {
    cat <<EOF >&2
Usage: $0 [--check] [patch|minor|major] [--push] [--yes] [--remote NAME] [--branch NAME]

  --check              Run validation and local tests only (no version bump)
  patch|minor|major    Semver bump (local commit + vX.Y.Z tag)
  --push               Push branch + tag (GitHub Release is created only after CI passes)
  --yes                Skip confirmation before --push
  --remote NAME        Git remote (default: origin)
  --branch NAME        Expected branch (default: master)

Examples:
  $0 --check
  $0 minor
  $0 minor --push
  $0 --push --yes patch
EOF
}

require_unreleased_notes() {
    if ! grep -q '^## \[Unreleased\]' "$CHANGELOG"; then
        echo "ERROR: CHANGELOG.md has no [Unreleased] section with notes to promote." >&2
        exit 1
    fi
    local content
    content="$(sed -n '/^## \[Unreleased\]/,/^## \[/{ /^## \[/d; /^$/d; p; }' "$CHANGELOG")"
    if [[ -z "$content" ]]; then
        echo "ERROR: [Unreleased] in CHANGELOG.md is empty." >&2
        echo "       Add release notes there before cutting a release." >&2
        exit 1
    fi
}

run_checks() {
    echo "==> Syntax check"
    bash -n bin/*.sh tests/run_*.sh scripts/*.sh

    echo "==> Changelog [Unreleased]"
    require_unreleased_notes
    echo "    [Unreleased] has notes"

    echo "==> Local tests"
    ./tests/run_local_tests.sh

    echo "==> All checks passed"
}

confirm_push() {
    local version="$1"
    if $FLAG_YES; then
        return 0
    fi
    local ans
    read -r -p "Push ${GIT_REMOTE}/${GIT_BRANCH} and tag v${version}? Release is created only if the tag workflow passes. [y/N] " ans
    case "$ans" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) echo "Aborted."; exit 1 ;;
    esac
}

push_release() {
    local version="$1"
    local current_branch

    current_branch="$(git branch --show-current 2>/dev/null || true)"
    if [[ -n "$current_branch" && "$current_branch" != "$GIT_BRANCH" ]]; then
        echo "ERROR: expected branch '${GIT_BRANCH}', currently on '${current_branch}'" >&2
        exit 1
    fi

    confirm_push "$version"

    echo "==> Pushing to ${GIT_REMOTE}"
    git push "$GIT_REMOTE" "$GIT_BRANCH"
    git push "$GIT_REMOTE" "v${version}"

    echo ""
    echo "Pushed ${GIT_BRANCH} and v${version}."
    echo "The GitHub Release is created only after .github/workflows/release.yml passes."
    echo "Watch: gh run watch --exit-status"
}

print_next_steps() {
    local version="$1"
    echo ""
    echo "Release prep done locally (v${version})."
    echo "  Push tag (Release after CI):  $0 ${BUMP_TYPE} --push"
    echo "  Or manually:"
    echo "    git push ${GIT_REMOTE} ${GIT_BRANCH}"
    echo "    git push ${GIT_REMOTE} v${version}"
    echo "  Do not run gh release create until the tag workflow is green."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) FLAG_CHECK=true; shift ;;
        --push) FLAG_PUSH=true; shift ;;
        --yes|-y) FLAG_YES=true; shift ;;
        --remote) GIT_REMOTE="${2:?--remote requires a value}"; shift 2 ;;
        --branch) GIT_BRANCH="${2:?--branch requires a value}"; shift 2 ;;
        major|minor|patch)
            if [[ -n "$BUMP_TYPE" ]]; then
                echo "ERROR: duplicate bump type '$1'" >&2
                usage
                exit 1
            fi
            BUMP_TYPE="$1"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument '$1'" >&2
            usage
            exit 1
            ;;
    esac
done

if $FLAG_CHECK; then
    if [[ -n "$BUMP_TYPE" || $FLAG_PUSH == true ]]; then
        echo "ERROR: --check cannot be combined with bump or --push" >&2
        exit 1
    fi
    run_checks
    exit 0
fi

if [[ -z "$BUMP_TYPE" ]]; then
    usage
    exit 1
fi

current_branch="$(git branch --show-current 2>/dev/null || true)"
if [[ -n "$current_branch" && "$current_branch" != "$GIT_BRANCH" ]]; then
    echo "ERROR: expected branch '${GIT_BRANCH}', currently on '${current_branch}'" >&2
    exit 1
fi

run_checks
echo ""
echo "==> Bumping version ($BUMP_TYPE)"
RELEASE_NO_PUSH_HINT=1 "$ROOT/scripts/bump-version.sh" "$BUMP_TYPE"

NEW_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

if $FLAG_PUSH; then
    push_release "$NEW_VERSION"
else
    print_next_steps "$NEW_VERSION"
fi
