# Lifecycle

Ask in chat and wait before `provision`, `deploy`, `destroy`, `suspend`, `resume`, `environment remove`, or `environment cleanup`. The request in the same message is not the yes. Provision and deploy each need their own yes, even when one question named both. `--yes` appears only after that follow-up confirmation. Config `set`, `init`, and `validate` stay ungated.

The question names the env and the effect. Provision creates the hosts. Deploy installs Splunk on the existing hosts. Destroy removes provider resources and keeps the registered env, `splunk_config.yml`, and state. `environment remove` drops the registry entry and is not destroy. `spa destroy --hosts` does not exist. Do not delete a live host from config and run `spa provision`.

Mutating commands pass `--env` or run with that env as cwd. If provision or deploy for that env is still running, stop that pid before destroy.

Phase lines, the provision/deploy/destroy lock, and the stderr sentence catalog are in the entry skill `## Long runs` section. Forward a phase line from stderr. On `ok: true` or `ok: false`, post the result only. Agent stdout is not a run log. Do not open `data.log` unless the user asked to debug a failure.

`spa hosts check` and `spa hosts check --hosts NAME_OR_ROLE` are the post-provision ping and `splunk_architecture` compare after the hosts exist. They take no AMI, key, or security-group arguments. Run that check before `spa run` when the playbook needs root. It is not the AWS selection check.
