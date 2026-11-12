# Upgrade

There is no `upgrade` subcommand. Discover playbooks with `spa run list`, then `spa run NAME --help`. Existing upgrade playbooks are `upgrade_splunk`, `upgrade_shc_rolling`, `upgrade_idxc_rolling`, and `upgrade_distributed` (`ansible/upgrade_splunk.yml` and the other upgrade `*.yml` files).

The ordered human runbook is [docs/upgrade.md](../../../../docs/upgrade.md). Mutating `spa run` needs `--yes` after a yes in chat. Before a playbook that needs root, run `spa hosts check`.
