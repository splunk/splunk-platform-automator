# Release process

Splunk Platform Automator is an Ansible/Terraform framework. A release is a **semver git tag plus a GitHub Release** whose notes come from `CHANGELOG.md`. There is no PyPI package or container image.

## Version source of truth

| Location | Purpose |
|----------|---------|
| `VERSION` | Canonical semver (`X.Y.Z`) |
| `CHANGELOG.md` | Keep a Changelog notes (`[Unreleased]` is promoted on bump) |
| Git tag `vX.Y.Z` | What users check out |
| GitHub Release | Release page + automatic source zip/tar |

```bash
cat VERSION
```

## Semver

- **MAJOR** — breaking config or playbook changes
- **MINOR** — new features (typical for a filled `[Unreleased]` bucket)
- **PATCH** — bug fixes and small improvements

## Checklist

1. Land changes on `master`.
2. Fill `## [Unreleased]` in `CHANGELOG.md` with what this version ships.
3. Run pre-release checks (local tests only; no AWS):

   ```bash
   ./scripts/release.sh --check
   ```

4. Cut the release (must be on `master`):

   ```bash
   ./scripts/release.sh minor              # local commit + tag only
   ./scripts/release.sh minor --push       # also push and create the GitHub Release
   ./scripts/release.sh minor --push --yes
   ```

   Also: `patch`, `major`. Flags can appear in any order.

5. If you skipped `--push`:

   ```bash
   ./scripts/release.sh minor --push
   # or:
   git push origin master && git push origin vX.Y.Z
   gh release create vX.Y.Z --title vX.Y.Z \
     --notes-file <(python3 scripts/changelog_notes.py X.Y.Z)
   ```

`--push` requires the [GitHub CLI](https://cli.github.com/) (`gh`) authenticated to this repo’s `origin`. It creates the GitHub Release from the new changelog section. The optional tag workflow (`.github/workflows/release.yml`) creates the same Release if the tag was pushed without `gh`.

## CI

On every pull request and every push to `master`, `.github/workflows/ci.yml` runs:

- `bash -n` on `bin/*.sh`, `tests/run_*.sh`, `scripts/*.sh`
- `./tests/run_local_tests.sh` (`pytest -m local`)

CI does **not** provision AWS, download Splunkbase apps, or read `config/splunk_config.yml`.

After the workflow exists, enable **branch protection on `master`**: require the `CI / Local tests` check, and disallow force-push.

## Manual lab / AWS (not in CI)

Run these when the delta warrants it (app routing, ITSI, Terraform), not for every patch. See [docs/App_Deployment_Testing.md](docs/App_Deployment_Testing.md).

```bash
ansible-playbook ansible/deploy_splunk_apps.yml -v
ansible-playbook ansible/verification/verify_app_deployment.yml -e fail_on_mismatch=true
# Full AWS pipeline (installers in ../Software/):
./tests/run_deployment_tests.sh
```

## What we do not do

- No moving `latest` tag
- No artifact publish beyond GitHub’s source archives
- No AWS or Splunkbase in GitHub Actions
- `release.sh --check` is for cutting a release; everyday PR validation is CI / `./tests/run_local_tests.sh`

## Quick reference

| Task | Command |
|------|---------|
| Show version | `cat VERSION` |
| Local tests | `./tests/run_local_tests.sh` |
| Pre-release check | `./scripts/release.sh --check` |
| Cut release | `./scripts/release.sh patch\|minor\|major` |
| Cut + publish | `./scripts/release.sh minor --push --yes` |
