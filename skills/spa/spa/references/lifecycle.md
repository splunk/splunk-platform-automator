# Lifecycle

Ask in chat and wait before `deploy`, `destroy`, `suspend`, `resume`, `environment remove`, or `environment cleanup`. The request in the same message is not the yes. `--yes` appears only after that follow-up confirmation. Config `set`, `init`, and `validate` stay ungated.

The question names the env and the effect. Deploy creates missing hosts if needed, then installs Splunk. To add a host on AWS or VirtualBox: `spa config add 'splunk_hosts[name=NAME]' '{"roles":[...]}' --yes`, `spa validate`, then `spa deploy --yes` after chat yes. External: `spa hosts register` then deploy. CCM host count is fixed at create; adding a name to a live CCM lab does not add an instance. Destroy removes provider resources and keeps the registered env, `splunk_config.yml`, and state. `environment remove` drops the registry entry and is not destroy. `spa destroy --hosts` does not exist. Do not delete a live host from config and run `spa deploy`.

Mutating commands pass `--env` or run with that env as cwd. If deploy or destroy for that env is still running, stop that pid before destroy.

Phase lines, the deploy/destroy lock, and the stderr sentence catalog are in [long-runs.md](long-runs.md). Load that file when running deploy, destroy, or `spa run`. Forward a phase line from stderr. On `ok: true` or `ok: false`, post the result only. Agent stdout is not a run log. Do not open `data.log` unless the user asked to debug a failure.

`spa hosts check` and `spa hosts check --hosts NAME_OR_ROLE` are the ping and `splunk_architecture` compare. They take no AMI, key, or security-group arguments. Run that check before `spa run` when the playbook needs root. It is not a required step after deploy. It is not the AWS selection check.
