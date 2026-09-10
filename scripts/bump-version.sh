#!/usr/bin/env bash
# Bump VERSION and promote CHANGELOG [Unreleased], then commit and tag vX.Y.Z.
# Usage: ./scripts/bump-version.sh patch|minor|major
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$PROJECT_ROOT/VERSION"
CHANGELOG="$PROJECT_ROOT/CHANGELOG.md"

if [[ $# -ne 1 ]] || [[ ! "$1" =~ ^(major|minor|patch)$ ]]; then
    echo "Usage: $0 <major|minor|patch>" >&2
    exit 1
fi

BUMP_TYPE="$1"

if [[ ! -f "$VERSION_FILE" ]]; then
    echo "ERROR: VERSION file not found at $VERSION_FILE" >&2
    exit 1
fi

CURRENT_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [[ ! "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "ERROR: Invalid version format in VERSION: '$CURRENT_VERSION'" >&2
    exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
case "$BUMP_TYPE" in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    patch) PATCH=$((PATCH + 1)) ;;
esac
NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
TODAY="$(date +%Y-%m-%d)"

if git -C "$PROJECT_ROOT" rev-parse "v${NEW_VERSION}" >/dev/null 2>&1; then
    echo "ERROR: tag v${NEW_VERSION} already exists" >&2
    exit 1
fi

github_release_url() {
    local url owner repo
    url="$(git -C "$PROJECT_ROOT" remote get-url origin 2>/dev/null || true)"
    url="${url%.git}"
    if [[ "$url" =~ github.com[:/]([^/]+)/([^/]+)$ ]]; then
        owner="${BASH_REMATCH[1]}"
        repo="${BASH_REMATCH[2]}"
        echo "https://github.com/${owner}/${repo}/releases/tag/v${NEW_VERSION}"
        return
    fi
    echo "https://github.com/splunk/splunk-platform-automator/releases/tag/v${NEW_VERSION}"
}

echo "Bumping version: $CURRENT_VERSION -> $NEW_VERSION"

echo "$NEW_VERSION" > "$VERSION_FILE"
echo "  Updated VERSION"

if [[ ! -f "$CHANGELOG" ]]; then
    echo "ERROR: CHANGELOG.md not found" >&2
    exit 1
fi

if ! grep -q '^## \[Unreleased\]' "$CHANGELOG"; then
    echo "ERROR: CHANGELOG.md has no ## [Unreleased] section to promote." >&2
    exit 1
fi

UNRELEASED_CONTENT="$(sed -n '/^## \[Unreleased\]/,/^## \[/{ /^## \[/d; /^$/d; p; }' "$CHANGELOG")"
if [[ -z "$UNRELEASED_CONTENT" ]]; then
    echo "ERROR: [Unreleased] in CHANGELOG.md is empty." >&2
    echo "       Add release notes there before cutting a release." >&2
    exit 1
fi

RELEASE_URL="$(github_release_url)"
python3 - "$CHANGELOG" "$NEW_VERSION" "$TODAY" "$RELEASE_URL" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
new_version, today, release_url = sys.argv[2], sys.argv[3], sys.argv[4]
text = path.read_text(encoding="utf-8")
old = "## [Unreleased]"
if old not in text:
    raise SystemExit("ERROR: CHANGELOG.md lost its [Unreleased] heading")
replacement = (
    f"{old}\n\n"
    f"## [{new_version}]({release_url}) - {today}"
)
path.write_text(text.replace(old, replacement, 1), encoding="utf-8")
PY
echo "  Updated CHANGELOG.md (promoted [Unreleased] to [${NEW_VERSION}])"

cd "$PROJECT_ROOT"
git add VERSION CHANGELOG.md
git commit -m "$(cat <<EOF
release: v${NEW_VERSION}

Bump version from ${CURRENT_VERSION} to ${NEW_VERSION}.
EOF
)"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"
echo "  Tagged v${NEW_VERSION}"

echo ""
echo "Done! Version bumped to $NEW_VERSION"
if [[ "${RELEASE_NO_PUSH_HINT:-}" != "1" ]]; then
    echo "  Push with: ./scripts/release.sh --push ${BUMP_TYPE}"
    echo "  Or: git push origin HEAD && git push origin v${NEW_VERSION}"
fi
