# Install Splunk Platform Automator

Primary path for operators: **install the framework once**, then `spa init` for each environment. Git clone remains the contributor path.

Do not copy `ansible/` into an environment directory. `SPA_HOME` is the install prefix (or clone). `SPA_ENV_DIR` is any directory `spa init` created.

## Installer (recommended)

Requires **Python 3.9+** with the `venv` module (`python3` on PATH). The installer creates a venv and `spa doctor` fails if that is missing or too old. Terraform is only required for AWS. The script always follows the newest GitHub Release (`releases/latest/download/install.sh`).

```sh
curl -fsSL https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh | sh
```

The script then downloads matching `spa-framework-*.tar.gz` from the same latest release (or `--version` / `SPA_VERSION`).

Defaults:

| Setting | Default | Override |
| --- | --- | --- |
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

Then follow the [user-guide start](user-guide.md#start-here). Keep each environment outside the replaceable install prefix.

Splunk installers and PS baseconfig apps stay **out of** `SPA_HOME` (`install.sh --force` deletes the prefix). Point at them once:

```bash
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa init --example cm_2idxc_sh_uf --provider aws ~/envs/my-env
```

That writes `${XDG_CONFIG_HOME:-~/.config}/spa/paths.yml` (directories only, not secrets). `spa init --software-dir` does the same and also copies `software_dir` / `baseconfig_dir` into the env `.spa.yml`. When a shared-path key is still unset, init stores the first explicit or discovered directory; it never replaces an established global with a later one-off init option. Optional: `--baseconfig-dir` (defaults to `--software-dir`). The installer does not create `~/.config/spa`. `spa validate` and `spa deploy` fail if those directories (and, for local apps, each named source) are still missing.

What to put in `Software/`: [Prepare Software](user-guide.md#prepare-software) (Linux tgz installers, PS baseconfig apps, optional `Splunk_Enterprise.lic`). Splunk / Cisco employees can download baseconfig apps from [https://go2.cisco.com/baseconfigs](https://go2.cisco.com/baseconfigs).

## Uninstall

`install.sh --uninstall --yes` removes the prefix (`SPA_HOME`) and the matching PATH wrapper (`~/.local/bin/spa` by default). It is **not** `spa destroy`: env dirs, Terraform state, and AWS stay untouched.

```bash
./install.sh --uninstall --yes
./install.sh --uninstall --yes --prefix /opt/spa --bindir ~/.local/bin
```

The prefix is deleted only if it looks like an SPA tree (`ansible.cfg`, `bin/spa`, `ansible/`). The wrapper is deleted only if it points at that prefix. Do not `rm -rf` a git clone you still need; uninstall is for an installed prefix. Agents must pass `--yes` (no interactive prompt).

## Extract anywhere

Build or download `spa-framework-X.Y.Z.tar.gz` (no wrapping directory). Unpack wherever you want:

```bash
mkdir -p ~/src/spa && tar -xzf spa-framework-X.Y.Z.tar.gz -C ~/src/spa
export SPA_HOME=~/src/spa
"$SPA_HOME/bin/spa" venv --shared --create --yes
export PATH="$SPA_HOME/bin:$PATH"
spa init --example cm_2idxc_sh_uf --provider aws ~/envs/my-env
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
bin/spa venv --shared --create --yes
spa doctor
```

Repair an existing shared venv with `spa venv --shared --reinstall --yes`, bump
packages and Ansible collections with `spa venv --shared --upgrade --yes`, or
delete and recreate it with `spa venv --shared --rebuild --yes`. These commands
target this `SPA_HOME` explicitly, even if the shell has a stale `SPA_VENV_DIR`.

Put Splunk installers and Professional Services baseconfig apps in a `Software/` directory as a sibling of the env (preferred) or of `SPA_HOME`. Checklist: [Prepare Software](user-guide.md#prepare-software). The full path contract is in the [user guide](user-guide.md#understand-the-paths).

## VirtualBox

Needed only when `virtualbox:` is in `splunk_config.yml`. `spa doctor --virtualbox` (or `spa doctor` from a VirtualBox env) checks Vagrant, VirtualBox, the driver match, and `vagrant-vbguest`. `spa hosts ssh` / `copy` use inventory.

**macOS (Homebrew):**

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/hashicorp-vagrant
brew install --cask virtualbox
vagrant plugin install vagrant-vbguest
```

Use HashiCorp's Vagrant formula. VirtualBox 7.2 needs Vagrant 2.4+; `spa doctor` fails if there is no driver for your VirtualBox. `vagrant-vbguest` is required so guests get Additions (clock skew without them). If a guest never comes up, destroy that host and run `spa provision --yes` / `spa deploy --yes` again.

**Linux:** [HashiCorp Linux packages](https://developer.hashicorp.com/vagrant/install#linux), then VirtualBox from the distro or [Oracle](https://www.virtualbox.org/wiki/Linux_Downloads):

```bash
# Debian/Ubuntu (after adding the HashiCorp apt repo)
sudo apt-get update && sudo apt-get install -y vagrant
sudo apt-get install -y virtualbox
vagrant plugin install vagrant-vbguest

# Fedora / RHEL (after adding the HashiCorp yum repo)
sudo dnf install -y vagrant VirtualBox
vagrant plugin install vagrant-vbguest
```

## WSL2

[Windows Subsystem for Linux](https://learn.microsoft.com/en-us/windows/wsl/install) can run SPA and drive VirtualBox on the Windows host.

1. Add this to `/etc/wsl.conf`, then run `wsl --shutdown` from Windows:

   ```ini
   [automount]
   options = "metadata"
   ```

2. Install the `virtualbox_WSL2` Vagrant plugin. This is a host prerequisite reported by `spa doctor`, not a daily operator command.
3. Export `VAGRANT_WSL_ENABLE_WINDOWS_ACCESS=1` and add the Windows VirtualBox directory (commonly `/mnt/c/Program Files/Oracle/VirtualBox`) to WSL `PATH`.

Day-to-day operation remains `spa provision`, `spa hosts ssh`, and the other commands in the [user guide](user-guide.md). Custom Python or Ansible pins for contributors: [contributing](contributing.md). Ansible comes from `spa_venv`, not a system install.

