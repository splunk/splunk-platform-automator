# Config header best practices

The config header is documentation. It records the design decisions from Phases 0a–9, so a later reader can see why the environment was built this way. Set it with `spa config header set`, not by editing the file. The field list is in `spa config header set --help`, and the value mapping is in [config-header-template.md](../assets/config-header-template.md).

## When to set the header

Set it after the operator approves the plan (Phase 6c) and before provisioning:

```
spa --agent config header set \
  --intent "config-test" \
  --requirements "single-node system for testing; 4 CPUs; RHEL 10" \
  --sva "S1 - lab single-node topology" \
  --placement "lab-minimal - single host runs indexer and search_head roles" \
  --os "RHEL 10; ssh_username=ec2-user" \
  --aws "eu-central-1; t3.xlarge (4 vCPUs); provider aws (chosen with --provider)" \
  --deploy "spa provision --yes && spa deploy --yes" \
  --yes
```

Agent mode needs `--yes`. Use `--dry-run` to preview. Omitted fields are removed, so send the full header each time.

## Fields

| Field | Purpose | Example |
| --- | --- | --- |
| `--intent` | Why the environment exists | `config-test`, `app-lab`, `production-like` |
| `--requirements` | Constraints and scale | `4 CPUs; 1TB ingestion; DR=multisite` |
| `--sva` | SVA topology class and lab gaps | `S1 (single-node)`, `M2 (lab gaps: ...)` |
| `--placement` | Where roles run | `lab-minimal`, `separate hosts`, `multisite` |
| `--license` | How Splunk is licensed | `trial`, or the license file in `splunk_defaults` |
| `--installer` | Splunk installer source | `Linux tgz from the Software directory` |
| `--os` | Operating system and SSH user | `RHEL 10; ssh_username=ec2-user` |
| `--aws` | AWS placement and API status | `eu-central-1; t3.xlarge; AWS API not available` |
| `--deploy` | Command that provisions and deploys | `spa provision --yes && spa deploy --yes` |

## Why it matters

- **Documentation:** future readers see the design decisions.
- **Audit trail:** the reason for each choice is recorded next to the config.
- **Onboarding:** a new team member sees the intent first.
- **Troubleshooting:** unexpected behavior can be matched against the stated intent and placement.

Never put a secret, token, password, or license body in a header field. The command refuses secret-shaped values, but do not rely on that check.
