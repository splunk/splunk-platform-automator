# Splunk Platform Automator

![Splunk Platform Automator Overview](https://github.com/splunk/splunk-platform-automator/blob/master/pic/splunk-platform-automator_overview.png)

![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Ansible](https://img.shields.io/badge/Ansible-2.10%2B-red.svg?logo=ansible&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg?logo=python&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-1.3.0%2B-purple.svg?logo=terraform&logoColor=white)

> **From architecture diagram to running Splunk cluster in less than an hour.**
> Splunk Platform Automator turns a single YAML file into a fully built,
> best-practice Splunk Enterprise environment: indexer clusters, multisite,
> search head clusters, forwarders, and the works. No hand-built hosts, no
> copy-pasting `.conf` files, no guessing at the bootstrap order.

SPA provisions and configures Splunk Enterprise—clustering, apps, AWS, VirtualBox, or existing hosts (external provider)—from **testing and training through staging and production**. One config file, one CLI: `spa`. The install follows Splunk best-practice config apps. There are many valid conf layouts; this is one automated path.

## Why SPA

Splunk Platform Automator is the deployment engine for the Splunk Enterprise
topologies you designed. Describe the environment once, then let SPA build it
the same way every time.

- **One file, the whole environment.** Describe your topology in
`splunk_config.yml` and let SPA handle the rest: hosts, cluster bootstrap,
and apps.
- **Ready-made topologies.** Examples cover single-node through multisite search
head clusters with Enterprise Security, so you start from a tested layout
instead of a blank page.
- **Your choice of infrastructure.** Provision on AWS with Terraform, spin up
local VirtualBox VMs, or deploy onto hosts you already have.
- **Best practices built in.** Base configuration apps, secrets from environment
lookups or Ansible Vault, and validation before anything is deployed.
- **Agent-ready.** `spa skills install cursor` links the `/spa`,  
`/spa-create-config`, and `/spa-apps` skills into Cursor, so an agent can  
design, validate, and deploy an environment with you, waiting for your yes at  
each step.

## Support

**This framework is not officially supported by Splunk.** It is developed on a best-effort basis.

## Features

- **Multiple environments:** `spa environment list`, `init`, `set`, and `remove` keep each lab or deployment in its own directory, with a default you can change.
- **Guided config editing:** `spa config set|add|merge|topology|provider` and `spa apps add|remove` make schema-checked edits with dry-run support, so you don't hand-edit `splunk_config.yml`. `spa config search` and `spa config explain` look up any setting.
- **Preflight checks:** `spa validate` checks the config, inventory, and license pairings. `spa doctor` checks host tools. A missing environment variable stops the run before anything changes.
- **Lifecycle control:** `spa suspend` and `spa resume` stop and start instances to save cost, and `spa destroy` removes the environment. Changing commands require an explicit `--yes`.
- **Run logs:** provision, deploy, and run write a log under the environment's `logs/` folder. `spa logs` replays any run, and live progress shows each step as it happens.
- **Playbook catalog:** `spa run list` shows the shipped playbooks, including rolling upgrades for indexer and search head clusters, plus your own. `spa run NAME --help` describes each one.
- **Verification:** verification playbooks confirm that deployed apps match the config.
- **Splunkbase and ITSI discovery:** `spa apps search` finds apps, `spa apps snippet` generates the config entry, and `spa apps content-packs list 5391` lists ITSI content packs and the command to add each one.
- **Existing hosts:** `spa init --provider external` with `spa hosts register` manages machines you already run. SPA does not create, stop, or terminate them.
- **Host access:** `spa hosts list --status`, `spa hosts ssh`, and `spa hosts copy` work with the hosts in your environment.
- **Shell completion:** `spa completion bash` and `spa completion zsh` add tab completion for commands, flags, and config paths.
- **Sizing guidance:** the `/spa-create-config` skill maps Splunk Validated Architectures to topologies and sizes replication and search factors.
- **Platform coverage:** Splunk 9 and 10 on Amazon Linux 2023, RHEL 10, and Ubuntu 24.04, on amd64 or arm64, with optional FIPS mode.

## Install

Requires **Python 3.9+** with the `venv` module (`python3` on PATH). The installer creates a virtualenv and fails if that interpreter is missing or too old.

```sh
curl -fsSL https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh | sh
spa skills install cursor
```

That installs the latest GitHub Release into `~/.local/share/spa` and puts `spa` on `PATH` via `~/.local/bin/spa`. Add `~/.local/bin` to `PATH` if `spa` is not found. Flags, uninstall, and clone/develop: [docs/install.md](docs/install.md). Put Splunk installers and PS baseconfig apps in a shared `Software/` directory ([Prepare Software](docs/user-guide.md#prepare-software)).

## Start here

```bash
spa doctor
spa init --example cm_2idxc_sh --provider aws ~/envs/my-env
cd ~/envs/my-env
spa validate
spa provision --yes && spa deploy --yes
```

VirtualBox: `--provider virtualbox` (for example `single_node`). Full narrative: [user guide](docs/user-guide.md).

Existing servers: `spa init --example TOPOLOGY --provider external ENV`, then `spa hosts register NAME --ssh-host HOST --user USER --key PATH --yes`.

## Docs

| Audience | Link |
| --- | --- |
| Humans (and agents following examples) | [docs/user-guide.md](docs/user-guide.md) |
| Command catalog (generated) | [docs/commands.md](docs/commands.md) · `spa agent schema --markdown` |
| Settings (generated) | [docs/config.md](docs/config.md) · `spa config schema --markdown` |
| Contributors | [docs/architecture.md](docs/architecture.md) · [docs/contributing.md](docs/contributing.md) |
| Agents | [AGENTS.md](AGENTS.md) |
| Config keys / snippets | `spa config explain` · [examples/catalog/features.yml](examples/catalog/features.yml) |
| Roadmap | [ROADMAP.md](ROADMAP.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Releases | [RELEASE.md](RELEASE.md) |
| Tests | [tests/README.md](tests/README.md) · `./tests/run_local_tests.sh` |

## License

Copyright 2022 Splunk Inc.

Licensed under the Apache License, Version 2.0. See [http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).
