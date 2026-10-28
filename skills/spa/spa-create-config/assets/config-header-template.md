# Config header fields

Do not paste a header into `config/splunk_config.yml`. Set it with `spa config header set`, which replaces the leading comment and removes any field you omit. The mapping below is the template: each line of the old header is one flag. Run `spa config header set --help` for the same list on the command line.

| Header line | Flag | Example value |
|-------------|------|---------------|
| Intent | `--intent` | `config-test`, `app-lab`, or `production-like` |
| Requirements | `--requirements` | `ingest=<band>; users=<band>; use_case=...; DR=<none\|multisite>` |
| SVA target | `--sva` | `S1` (lab compromises: list the gaps) |
| Role placement | `--placement` | `lab-minimal - one host runs indexer and search head` |
| License | `--license` | `trial`, or the license file set in `splunk_defaults` |
| Installer | `--installer` | `Splunk Enterprise Linux tgz from the Software directory` |
| OS | `--os` | `RHEL 10; ssh_username=ec2-user` |
| AWS | `--aws` | `eu-central-1; t3.xlarge; AWS API: not available` (when you skipped the API) |
| Deploy | `--deploy` | `spa provision --yes && spa deploy --yes` |

Example, with the operator's confirmation first:

```
spa --agent config header set --intent config-test --sva S1 --placement "lab-minimal - one host" --os "RHEL 10; ssh_username=ec2-user" --deploy "spa provision --yes && spa deploy --yes" --yes
```

Agent mode needs `--yes`. Use `--dry-run` to preview. A line break, a certificate or license marker, or a secret-shaped value is refused. Leave out any field the operator did not supply.
