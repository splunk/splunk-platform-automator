# Release process

Splunk Platform Automator is an Ansible/Terraform framework. A release is a **semver git tag plus a GitHub Release** whose notes come from `CHANGELOG.md`. The Release also attaches the operator **framework tarball** and **`install.sh`**. There is no PyPI package or container image.

## Version source of truth

| Location | Purpose |
|----------|---------|
| `VERSION` | Canonical semver (`X.Y.Z`) |
| `CHANGELOG.md` | Keep a Changelog notes (`[Unreleased]` is promoted on bump) |
| `docs/commands.md` | Regenerated on bump (`spa --no-agent agent schema --markdown`) |
| Git tag `vX.Y.Z` | What users check out |
| GitHub Release | Release page + `install.sh` + `spa-framework-X.Y.Z.tar.gz` (plus GitHub’s automatic source zip/tar). Operators curl `https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh`. |

```bash
cat VERSION
```

## Semver

- **MAJOR** — breaking config or playbook changes
- **MINOR** — new features (typical for a filled `[Unreleased]` bucket)
- **PATCH** — bug fixes and small improvements

## Checklist

1. Land changes on `master`.
2. Fill `## [Unreleased]` in `CHANGELOG.md` with what this version ships. `docs/commands.md` is regenerated in the bump commit (do not hand-edit it).
3. Optionally run local tests (also what CI runs on the tag):

   ```bash
   ./scripts/release.sh --check
   ```

4. Cut the release (must be on `master`; this does **not** re-run the test suite):

   ```bash
   ./scripts/release.sh minor              # local commit + tag only
   ./scripts/release.sh minor --push       # push master + tag; wait for CI
   ./scripts/release.sh minor --push --yes
   ```

   Also: `patch`, `major`. Flags can appear in any order.

5. If you skipped `--push`:

   ```bash
   ./scripts/release.sh minor --push
   # or:
   git push origin master && git push origin vX.Y.Z
   ```

`--push` only pushes `master` and `vX.Y.Z`. The GitHub Release is created by [`.github/workflows/release.yml`](.github/workflows/release.yml) **after** local tests pass on that tag. Notes come from `CHANGELOG.md` plus a Full changelog link to that tag (same footer as v2.4.0). If the tag workflow fails, you get a tag but **no** Release page. Do not run `gh release create` until that workflow is green (or you are intentionally publishing a known-good tag).

## CI

On every pull request and every push to `master`, `.github/workflows/ci.yml` runs:

- `bash -n` on `bin/*.sh`, `tests/run_*.sh`, `scripts/*.sh`
- `./tests/run_local_tests.sh` (`pytest -m local`)

CI does **not** provision AWS, download Splunkbase apps, or read `config/splunk_config.yml`.

After the workflow exists, enable **branch protection on `master`**: require the `CI / Local tests` check, and disallow force-push.

Merged PR head branches are deleted automatically (`delete_branch_on_merge` on the GitHub repo). This is a repository setting, not an in-tree file: Settings → General → Pull Requests → **Automatically delete head branches**.

## Manual lab / AWS (not in CI)

Run these when the delta warrants it (app routing, ITSI, Terraform), not for every patch. See [tests/README.md](tests/README.md).

```bash
ansible-playbook ansible/splunk_apps_deploy.yml -v
ansible-playbook ansible/verification/verify_app_deployment.yml -e fail_on_mismatch=true
# Full AWS pipeline (installers in ../Software/):
./tests/run_deployment_tests.sh
```

## What we do not do

- No moving `latest` tag
- No PyPI package or container image
- No AWS or Splunkbase in GitHub Actions
- `release.sh --check` is optional local validation; `patch|minor|major` and `--push` do not re-run tests (the tag workflow does)

## Quick reference

| Task | Command |
|------|---------|
| Show version | `cat VERSION` |
| Local tests | `./tests/run_local_tests.sh` |
| Pre-release check | `./scripts/release.sh --check` |
| Cut release | `./scripts/release.sh patch\|minor\|major` |
| Cut + push tag | `./scripts/release.sh minor --push --yes` (Release after tag CI) |
