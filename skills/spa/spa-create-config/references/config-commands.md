# Config change commands

Reference for `spa-create-config`. Use these commands for every config change. Never hand-edit `splunk_config.yml`.

Always use these commands, never hand-edit:
| Change | Correct Command | Why |
|--------|-----------------|-----|
| Set a scalar (region, instance type, OS) | `spa --env NAME config set PATH VALUE --yes` | Schema validation, audit trail |
| Add a host | `spa --env NAME config add 'splunk_hosts[name=HOSTNAME]' '{"roles":[...], ...}' --yes` | SPA validates role constraints, cluster membership, site mapping |
| Add an indexer cluster | `spa --env NAME config set splunk_idxclusters[idxc_name=idxc1].idxc_rf 3 --yes` | Constraints checked against peer count |
| Add an app | `spa --agent apps search QUERY` then `spa --env NAME apps add APP_ID --roles ROLE1,ROLE2 --yes` | Validates app exists, role exists, app not duplicate |
| Add ITSI content pack | `spa --agent apps content-packs list 1841` then `spa --env NAME apps add 1841 --content-pack CP_NAME --yes` | Pack name validated against ITSI manifest |
| Change OS | `spa --env NAME config merge --file -` with YAML input | Ensures os.ssh_username, disable_apparmor are set together |
| Merge multiple settings | `spa --env NAME config merge --file FILE.yml --yes` | Atomic, all-or-nothing; validation happens once |
| Move a role to another host | `spa --env NAME config move role ROLE --from HOST --to HOST --yes` | Relocates one role; required on path B when an extra role must leave a co-located preset host |
| Rename, prefix, or postfix hosts | `spa --env NAME config move host OLD --to NEW --yes` or `--prefix PREFIX` or `--postfix POSTFIX` | Rewrites host identities and host-name references |
| Read current state | `spa --env NAME config get [PATH]` | Always check before assuming a value |
| Search for a path | `spa --env NAME config search KEYWORD` | Finds related config paths |
| Explain a path | `spa --env NAME config explain PATH` | Shows type, constraints, examples, related commands |
| Preview a write | `spa --env NAME config set PATH VALUE --show-diff --yes` | Human-only redacted hunk; agent JSON already has `data.diff` |
| Confirm an identity | `spa --env NAME config get 'splunk_hosts[name=HOSTNAME].roles'` | `found: true` on a hit; `found: false` plus `reason` on a miss |

## After every write

1. Inspect `changed` and `ready`. `ok: false` with `ready: false` wrote nothing.
2. Humans: `--show-diff` for the redacted hunk. Agents already get `data.diff`.
3. `spa config get` the identity and confirm `found: true`.
4. `spa validate` before provision or deploy.

## Terminology

Use consistently: `cluster_manager`, `terraform.aws`, `splunk_hosts`, `plugin: splunk-platform-automator` (not "master").
