# Splunk Platform Automator

![Splunk Platform Automator Overview](https://github.com/splunk/splunk-platform-automator/blob/master/pic/splunk-platform-automator_overview.png)

![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Ansible](https://img.shields.io/badge/Ansible-2.10%2B-red.svg?logo=ansible&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg?logo=python&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-1.3.0%2B-purple.svg?logo=terraform&logoColor=white)

SPA provisions and configures Splunk Enterprise—clustering, apps, AWS or VirtualBox—from **testing and training through staging and production**. One config file, one CLI: **`spa`**. The install follows Splunk best-practice config apps. There are many valid conf layouts; this is one automated path.

## Support

**This framework is not officially supported by Splunk.** It is developed on a best-effort basis.

## Features

- Reproducible Splunk Enterprise: cluster manager, indexer clusters, deployer, search head clusters, deployment server, forwarders, license manager, monitoring console
- One YAML definition (`splunk_config.yml`); topology examples composed at `spa init`
- **Apps:** Splunkbase, local, or URL via `splunk_app_deployment` — [Apps](docs/apps.md)
- **Secrets:** environment lookups or Ansible Vault — [Secrets](docs/secrets.md)
- **AWS:** Terraform from the same config (`spa provision` / `destroy`)
- **VirtualBox:** local VMs through `spa` (Vagrant only as an implementation detail)

## Start here

```bash
spa doctor
spa init --example cm_2idxc_sh_uf --provider aws ~/envs/my-env
cd ~/envs/my-env
spa validate
spa provision --yes && spa deploy --yes
```

VirtualBox: `--provider virtualbox` (for example `single_node`). Installer: [docs/install.md](docs/install.md). Full narrative: [user guide](docs/user-guide.md).

## Docs

| Audience | Link |
| --- | --- |
| Humans (and agents following examples) | [docs/user-guide.md](docs/user-guide.md) |
| Agents | [AGENTS.md](AGENTS.md) |
| Config keys / snippets | `spa features list` · [examples/catalog/features.yml](examples/catalog/features.yml) |
| Roadmap | [ROADMAP.md](ROADMAP.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Releases | [RELEASE.md](RELEASE.md) |
| Tests | [tests/README.md](tests/README.md) · `./tests/run_local_tests.sh` |

## License

Copyright 2022 Splunk Inc.

Licensed under the Apache License, Version 2.0. See [http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).
