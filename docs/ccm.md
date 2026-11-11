# CCM (employee-only)

Corporate Cloud Manager is a REST portal over AWS for Splunk staff with CCM access. SPA provisions CCM **EC2** deployments and then installs Splunk with the usual Ansible path. This is **not** Terraform (`terraform.aws`) and **not** a CCM Splunk install (`?type=splunk`). Public labs stay `--provider aws`, `virtualbox`, or `external`.

Human `spa --help`, invalid-choice text, and skills omit CCM unless `CCM_TOKEN` is set, the env already has a root `ccm:` block, or the operator already named CCM. Typing `spa provider ccm …` still works; a missing token fails at runtime as **set / not set**.

## Discover and configure

Auth is `CCM_TOKEN` in the process environment (`lookup('env', 'CCM_TOKEN')`). It is not a config key. Mint the PAT in the CCM UI. `spa doctor` and `spa provider ccm check-auth` report the env var as **set / not set** and never print the token.

`spa config provider ccm` writes the `ccm:` YAML block. `spa provider ccm` is discovery, not that write:

```bash
spa provider ccm check-auth
spa provider ccm survey
spa provider ccm operating-systems list
spa provider ccm instance-types list
spa provider ccm disk-storage list
spa provider ccm ssh-keys list
spa config explain provider.ccm
```

Size OS, instance type, and disk from that live catalog. Do not hardcode those lists. GUI closed sets (`business_purpose`, `operation_hours`) are `spa provider ccm business-purposes list` and `operation-hours list`.

`ccm.ssh_username` is always `splunker` for every CCM OS flavor. Operators create the SSH key in the CCM GUI, set `ccm.key_name`, and keep the private file locally. `spa provider ccm ssh-keys list` shows CCM names and whether the local file exists. SPA does not create keys or download PEM material.

CCM is remote (like AWS). After an explicit yes, `spa config merge remote-provider --yes`.

## Provision and deploy

```bash
spa init --example TOPOLOGY --provider ccm ENV
spa validate
spa provision --yes
spa deploy --yes
```

`spa validate` rejects `ttl_days` outside 1–30, host count over 50, a derived CCM deployment name that is not 5–100 letters/numbers/hyphens/underscores (set `ccm.name` when the env directory basename does not match), a missing local private key file, mixed `external:` hosts (CCM envs cannot mix external hosts in v1), and (when `CCM_TOKEN` is set) an unknown `key_name` or an account that would exceed 100 non-terminated instances. The cap counts this env's hosts once (it leaves the recorded `ccm/state.json` deployment out of the live total). `spa provision` refuses the same mix and does not create a deployment. Provision creates one CCM EC2 deployment and writes `$SPA_ENV_DIR/ccm/state.json` as soon as CCM returns a deployment id (never the PAT), then polls until ready and writes inventory. `spa provision` again while that id is live or pending is refused before confirmation (`already provisioned: ID`); run `spa destroy --yes` to replace the lab. The TTL warning uses controller-local time (same spelling as `spa hosts list --status`) and prints after a successful provision, including with `--yes`. An expired id uses the TTL hint: `spa destroy --yes` then `spa provision --yes`. CCM terminates the **whole deployment** when TTL expires.

## Operate the environment

| Job | Command |
| --- | --- |
| Inspect CCM host status | `spa hosts list --status` |
| Stop instances, retain disks | `spa suspend --yes` |
| Start and refresh inventory addresses | `spa resume --yes` |
| Stay up after a business-hours stop | `spa provider ccm operation-hours set manual --yes` then `spa resume --yes` |
| Extend TTL (new expiry = now + N days, 1–30) | `spa provider ccm ttl extend --days N --yes` |
| Reconcile Splunk after resume/change | `spa deploy --yes` |
| Tear down the CCM deployment and local state | `spa destroy --yes` |

`spa resume --yes` is the wake-up after either `spa suspend` or a CCM business-hours stop. It polls until selected instances are `running` with an `ip_address`, then refreshes inventory. `wait=False` skips that poll and the inventory refresh. `spa suspend --yes` waits for `stopped` the same way. Resume does not change `operation_hours`. If live hours are still `business_hours` (from `ccm/state.json` after `spa provider ccm operation-hours set`, otherwise YAML) and the current time in the deployment timezone is outside Monday–Friday 08:00–18:00, SPA warns that CCM may stop the instances again.

When TTL has expired, the deployment is gone. `spa resume` / `suspend` / `deploy` cannot bring it back. `spa destroy --yes` clears local state (a missing CCM deployment is success). A new lab is `spa provision --yes`.
