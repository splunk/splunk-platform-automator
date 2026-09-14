# Install Splunk Platform Automator

Primary path for operators: **install the framework once**, then `spa init` for each environment. Git clone remains the contributor path.

Do not copy `ansible/` into an environment directory. `SPA_HOME` is the install prefix (or clone). `SPA_ENV_DIR` is any directory `spa init` created.

## Installer (recommended)

Needs Python 3.9+ with the `venv` module. Terraform is only required for AWS.

After a GitHub Release (`gh auth login` if the repo is private):

```bash
gh release download --repo splunk/splunk-platform-automator --pattern install.sh -O - | sh
```

Or from GitHub once `main` has `install.sh`:

```bash
curl -fsSL https://raw.githubusercontent.com/splunk/splunk-platform-automator/main/install.sh | sh
```

Defaults:

| Setting | Default | Override |
|---------|---------|----------|
| Prefix (`SPA_HOME`) | `~/.local/spa` | `--prefix` or `SPA_PREFIX` |
| Wrapper on `PATH` | `~/.local/bin/spa` | `--bindir` or `SPA_BINDIR` |
| Release | latest | `--version X.Y.Z` or `SPA_VERSION` |

The installer unpacks the framework tarball, runs `bin/spa_venv.sh --create`, and writes a `spa` wrapper that execs `$SPA_HOME/.venv/bin/python`. Add `~/.local/bin` to `PATH` if it is not already.

From a checkout or an already extracted tarball:

```bash
./install.sh --prefix ~/.local/spa
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
