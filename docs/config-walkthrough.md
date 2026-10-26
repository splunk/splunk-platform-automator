# Build a clustered ITSI config

This is a copy-paste example of `spa config` and `spa apps`. It builds an AWS
lab with an indexer cluster, a search-head cluster, ITSI, two content packs,
one additional app, and a standalone search head. It stops at `spa validate`.
Provisioning remains your own follow-up.

Look up each setting before writing it: `spa config search QUERY`, then
`spa config explain PATH`. Explain describes one level and prints one
command. A deeper level is a longer path. Explain does not change the file.

Run the commands from the directory where the lab should be created. `spa init`
creates `./itsi-lab` there.

## Before you start

The composed topology references `SPLUNK_ADMIN_PASSWORD`, `SPLUNK_IDXC_PASSWORD`,
and `SPLUNK_SHC_PASSWORD`. Later steps add `SPLUNKBASE_USERNAME` and
`SPLUNKBASE_PASSWORD`. Export each name to a non-empty value with your
shell's secret mechanism. Do not put the values in this file or in shell
history.

`spa init` prints each referenced name as `set` or `not set` and still
creates the environment. `spa validate` fails before it inspects the inventory
when any referenced variable is missing or empty. Immediately after init, with
those three passwords unset, the error is:

```text
Environment variables required by splunk_config.yml are not set: SPLUNK_ADMIN_PASSWORD, SPLUNK_IDXC_PASSWORD, SPLUNK_SHC_PASSWORD.
Export each variable to a non-empty value and rerun the command.
```

The error lists variable names only.

## 1. Create the AWS environment

```bash
spa init --example cm_2idxc_3shc_ds --provider aws ./itsi-lab
cd itsi-lab
```

This copies the shipped AWS block: region `eu-central-1`, AMI
`ami-0443f7d10da53831f`. The example comments that id as RHEL 10 hourly in
`eu-central-1`, and `spa init` copies the comment onto `ami_id`. That image
does not include `acl` or PolicyKit. The block
also copies key pair `aws_key`, private key `~/.ssh/aws_key.pem`, security
group `Splunk_Basic`, instance type `t3.medium`, and a 50 GB `gp3` volume.
It does not call AWS. The hosts are `cm`, indexers `idx1` and `idx2`, search
heads `sh1` through `sh3` in `shc1`, and `ds`, which is the deployment server and the deployer.

## 2. Set the image and size the indexers and search-head cluster

The image is one global value, so it uses `config set`. The search-head
cluster instance type uses the same command with a host selector. The
indexer instance type is the same change written as a fragment.

```bash
spa config explain terraform.aws.ami_id
spa config set terraform.aws.ami_id ami-0f5fb818aeff8f5fb --yes
spa config explain splunk_hosts.terraform.aws.instance_type
spa config set 'splunk_hosts[iter.prefix=sh].terraform.aws.instance_type' c5.4xlarge --yes
mkdir -p fragments
cat > fragments/indexer-size.yml <<'EOF'
splunk_hosts:
  - iter:
      prefix: idx
      numbers: 1..2
    terraform:
      aws:
        instance_type: c5.4xlarge
EOF
spa config merge --file fragments/indexer-size.yml --yes
```

The first `config set` replaces the provider AMI for every host. When AWS
can describe that id, the same command replaces the comment with the image
name and description. Without credentials the id is still saved and the old
image comment is removed. The second sets `c5.4xlarge` on the `shc1`
members. The fragment does the same for the
indexer range. Both ranges use the global image. `cm`, `ds`, and the
standalone search head added later keep `t3.medium`.

## 3. Look up packages and hosts

```bash
spa config explain
spa config search packages
spa config explain os
spa config explain os.packages
spa config explain splunk_hosts
spa config explain splunk_hosts.os.packages
```

Bare `spa config explain` lists the top-level sections. Search prints
`os.packages` and `splunk_hosts.os.packages`. The first line says all hosts.
The second says per-host and names the global list. Explain `os` for when
that block applies, then `os.packages`. That page prints `SCOPE` with the
per-host path, and this command:

```text
spa config set os.packages '["acl", "polkit"]'
```

Leave that command unrun. This walkthrough does not put `acl` or `polkit` in
`splunk_config.yml`. On deploy, the common role installs `acl` on every
non-Windows host and the PolicyKit package for the OS (`polkit` on this RHEL
image, `policykit-1` on Debian-family). Those packages are added beside any
`os.packages` you set.

`splunk_hosts` is the host entry. Choose one identity, `name`, `list`, or
`iter`, then set shared fields such as `roles` and `os`.
`splunk_hosts.os.packages` is the per-host package list. Its page says Java
21 belongs on the search host, and it prints a `config set` for one named
host. Step 7 uses `merge` instead, so the ITSI license and the search-head
package are one edit. Java stays off the global `os` block.

## 4. Preview the ITSI requirements

```bash
spa apps add 1841 --dry-run
```

ITSI is not written yet. The output names the missing license manager,
license file, and Java 21 package. This example already records the admin
password lookup. If a config does not, run
`spa config set splunk_defaults.splunk_admin_password --from-env SPLUNK_ADMIN_PASSWORD --yes`.

## 5. Download installers, name the hosts, and turn on TLS

```bash
spa config set splunk_defaults.splunk_download.splunk true --yes
spa config set splunk_defaults.splunk_download.splunkforwarder true --yes
spa config set splunk_defaults.splunk_set_servername true --yes
spa config set splunk_defaults.splunk_set_default_hostname true --yes
spa config set splunk_defaults.splunk_loginpage_print_userpw false --yes
spa config set splunk_defaults.splunk_ssl.web.enable true --yes
spa config set splunk_defaults.splunk_ssl.inputs.enable true --yes
spa config set splunk_defaults.splunk_ssl.outputs.enable true --yes
```

Boolean values are JSON, so `true` and `false` are unquoted. Download fetches
the Enterprise and universal-forwarder archives into Software during deploy.
The hostname settings write the inventory name into Splunk `serverName` and
the default event host. The login page does not print the admin password.
TLS is enabled for Splunk Web, receiving inputs, and forwarding outputs.
These commands do not install your own certificates.

## 6. Add a management host

```bash
spa config explain splunk_hosts.roles
mkdir -p fragments
cat > fragments/management-host.yml <<'EOF'
splunk_hosts:
  - name: lm
    roles:
      - license_manager
EOF
spa config merge --file fragments/management-host.yml --resolve splunk_defaults.splunk_license_file Splunk_Enterprise.lic --yes
```

`ds` is already the deployment server and the only deployer for `shc1`. `lm`
is added as the license manager and does not take the deployer role: `shc1`
cannot have two. The license manager cannot be saved without a license
file, so the Enterprise filename is supplied on that command. `cm` stays
the cluster manager and monitoring console.

## 7. Add the ITSI license and Java

```bash
mkdir -p fragments
cat > fragments/license-and-java.yml <<'EOF'
splunk_defaults:
  splunk_license_file:
    - Splunk_ITSI.lic
splunk_hosts:
  - iter:
      prefix: sh
      numbers: 1..3
    os:
      packages: [java-21-openjdk]
EOF
spa config merge --file fragments/license-and-java.yml --yes
```

`merge` adds `Splunk_ITSI.lic` beside the Enterprise license. Both names are
basenames in the Software directory. The same fragment appends
`java-21-openjdk` to the search-head hosts. That package name matches Amazon
Linux and RHEL. `acl` is not in this fragment. Deploy still installs it.

## 8. Add ITSI and two content packs

Before selecting packs, inspect the exact Content Library release:

```text
spa apps content-packs list 5391
```

The command uses `--archive`, a matching archive in `apps_dir`, an install archive already in the app temp directory, or cached pack `app.conf` files. An install archive is left in place. `--version` selects a release; the default `latest` replaces the `app.conf` cache when Splunkbase has a newer one. A download says so before it starts, and that downloaded archive is removed.
It lists the exact folder names, what each archive says it provides, and any
matching SPA post-install automation. The Unix and Windows rows print the two
selection commands used below.

```bash
spa apps add 1841 --yes
spa apps add 5391 --content-pack DA-ITSI-CP-nix --content-pack DA-ITSI-CP-windows --yes
cat > fragments/content-pack-customizations.yml <<'EOF'
splunk_app_deployment:
  apps:
    - app_id: 5391
      content_pack_apps:
        - name: DA-ITSI-CP-nix
          customizations:
            run_playbook_after_restart: ansible/apps_playbooks/DA-ITSI-CP-nix_configure.yml
            force_run_playbook_after_restart: false
        - name: DA-ITSI-CP-windows
          customizations:
            run_playbook_after_restart: ansible/apps_playbooks/DA-ITSI-CP-windows_configure.yml
            force_run_playbook_after_restart: false
EOF
spa config merge --file fragments/content-pack-customizations.yml --yes
```

Every search head is in `shc1`, so ITSI does not need `shc_whitelist` yet.
The content-pack command keeps the ITSI entry and records the two named packs.
Each pack runs its configuration playbook after the restart caused by
installation. `force_run_playbook_after_restart: false` prevents that
playbook from running again when the pack did not change.

## 9. Add the ITSI prerequisite apps

```bash
spa apps add 2882 --roles search_head --yes
spa apps add 2890 --roles search_head --yes
spa config set 'splunk_app_deployment.apps[app_id=2890].customizations.run_playbook' ansible/apps_playbooks/Splunk_ML_Toolkit-configure.yml --yes
spa apps add 1621 --roles search_head --yes
```

These add Python for Scientific Computing, the Machine Learning Toolkit, and
the Common Information Model to the search tier. The MLTK customization runs
its configuration playbook after the app is installed. The same playbook can
be attached while adding the app: `spa apps add 2890 --roles search_head --customize --yes`.

## 10. Search for the Unix add-on

```bash
spa apps search unix
```

A keyword is enough. The matching row is Splunkbase app id `833`, folder name
`Splunk_TA_nix`, title Splunk Add-on for Unix and Linux. A `playbook` marker
on that row means a curated customization can be attached with `--customize`.

## 11. Add an app for the universal forwarder

```bash
spa apps add 833 --roles universal_forwarder --customize --yes
```

`--customize` attaches `ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml`.
That playbook enables the TA-nix metric script inputs and sends them to the
`itsi_im_metrics` index.

## 12. Show why a standalone search head needs a filter

```bash
cat > fragments/shs.yml <<'EOF'
splunk_hosts:
  - name: shs
    roles: [search_head]
    os:
      packages: [java-21-openjdk]
EOF
spa config merge --file fragments/shs.yml --yes
```

This command exits 0, prints `itsi.search_tier`, and does not change the
file. ITSI would otherwise target both `shc1` and standalone `shs`. The retry
line names the filter to add.

## 13. Keep ITSI on the search-head cluster

```bash
spa config merge --file fragments/shs.yml --resolve 'splunk_app_deployment.apps[app_id=1841].shc_whitelist' '["shc1"]' --yes
```

One transaction adds `shs`, gives it Java, and sets `shc_whitelist` to
`shc1`. The resolve value replaces that field.

## 14. Review and validate

```bash
spa config get --full
spa validate
```

Export every referenced variable before `spa validate`. The command fails
until `SPLUNK_ADMIN_PASSWORD`, `SPLUNK_IDXC_PASSWORD`, `SPLUNK_SHC_PASSWORD`,
`SPLUNKBASE_USERNAME`, and `SPLUNKBASE_PASSWORD` are non-empty. Put
`Splunk_Enterprise.lic` and `Splunk_ITSI.lic` in the Software directory before
validation. Inventory also expects the usual Splunk installer archive in that
directory.

## Provision it yourself

Confirm the AMI, key pair, security group, and region, then run:

```bash
spa provision --yes && spa deploy --yes
```

Those commands are not part of the checked transcript above.
