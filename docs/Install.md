# Install Splunk Platform Automator

Primary path for operators: **install the framework once**, then `spa init` for each environment. Git clone remains the contributor path.

Do not copy `ansible/` into an environment directory. `SPA_HOME` is the install prefix (or clone). `SPA_ENV_DIR` is any directory `spa init` created.

## Installer (recommended)

Needs Python 3.9+ with the `venv` module. Terraform is only required for AWS.

From **3.0**, `install.sh` is a GitHub Release asset. `releases/latest/download/install.sh` always follows the newest published `v*` release (not `main`). Use **bash**, not `sh`.

Public repo (or once release assets are public):

```bash
/bin/bash -c "$(curl -fsSL https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh)"
```

Pass installer flags after `--` when piping:

```bash
curl -fsSL https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh | bash -s -- --prefix /opt/spa
```

Private repo (`gh auth login`):

```bash
gh release download --repo splunk/splunk-platform-automator --pattern install.sh -O - | bash
```

The script then downloads matching `spa-framework-*.tar.gz` from the same latest release (or `--version` / `SPA_VERSION`). That URL 404s until the first 3.0 GitHub Release exists.

Defaults:

| Setting | Default | Override |
|---------|---------|----------|
| Prefix (`SPA_HOME`) | `${XDG_DATA_HOME:-~/.local/share}/spa` | `--prefix` or `SPA_PREFIX` |
| Wrapper on `PATH` | `~/.local/bin/spa` | `--bindir` or `SPA_BINDIR` |
| Release | latest | `--version X.Y.Z` or `SPA_VERSION` |

A relative `XDG_DATA_HOME` is ignored (XDG spec); the prefix then falls back to `~/.local/share/spa`. The installer does not create `~/.config/spa` or `~/.local/state/spa`. Env config and Terraform state stay in each `SPA_ENV_DIR`.

The installer unpacks the framework tarball, runs `bin/spa_venv.sh --create`, and writes a `spa` wrapper that execs `$SPA_HOME/.venv/bin/python`. Add `~/.local/bin` to `PATH` if it is not already.

From a checkout or an already extracted tarball:

```bash
./install.sh
./install.sh --from spa-framework-X.Y.Z.tar.gz --prefix /opt/spa --bindir ~/.local/bin
```

`--force` replaces an existing prefix. `--skip-venv` / `--skip-doctor` skip those steps.

Then:

```bash
spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env
cd ~/envs/my-env
spa validate
spa provision --yes && spa deploy --yes
```

## Extract anywhere

Build or download `spa-framework-X.Y.Z.tar.gz` (no wrapping directory). Unpack wherever you want:

```bash
mkdir -p ~/src/spa && tar -xzf spa-framework-X.Y.Z.tar.gz -C ~/src/spa
export SPA_HOME=~/src/spa
"$SPA_HOME/bin/spa_venv.sh" --create
export PATH="$SPA_HOME/bin:$PATH"
spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env
```

`bin/spa` resolves the framework from its own path, so a symlink to `$SPA_HOME/bin/spa` is enough if that tree stays put. The installer wrapper also sets `SPA_HOME` and prefers the prefix venv.

Pack a tarball from a checkout:

```bash
./scripts/pack-framework.sh -o spa-framework-$(cat VERSION).tar.gz
```

The archive excludes `tests/`, `.git`, GitHub workflows, and lab `config/` / `inventory/`.

## Develop SPA (git clone)

```bash
git clone https://github.com/splunk/splunk-platform-automator.git
cd splunk-platform-automator
source bin/spa_venv.sh --create
spa doctor
```

Put Splunk installers and Professional Services baseconfig apps in a `Software/` directory as a sibling of the env (preferred) or of `SPA_HOME`. See the [README](../README.md#framework-installation).
