# Prerequisites

Run `spa doctor` and `spa validate` before mutating infrastructure.

A missing local Splunk archive message names the glob, the resolved Software directory, and one download page. Repeat that message. Do not download the file.

- Enterprise: https://www.splunk.com/en_us/download/splunk-enterprise.html
- Universal Forwarder (Linux tgz and Windows MSI): https://www.splunk.com/en_us/download/universal-forwarder.html

The local installer stays in the Software directory when `splunk_download.splunk` or `splunk_download.splunkforwarder` is true. The host URL uses that file's basename. The build number is in the filename and cannot be guessed.

Missing credentials are reported as **set** or **not set**. Repeat the names from `spa validate`. Never print a value. Never suggest `echo`, `printenv`, `env | grep`, or a zsh indirect expansion.

- Splunkbase, when an app will be downloaded: `SPLUNKBASE_USERNAME` and `SPLUNKBASE_PASSWORD`.
- AWS, when `spa aws --check-auth` fails: prefer `AWS_PROFILE`; otherwise name `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, plus `AWS_SESSION_TOKEN` for temporary credentials.

`spa validate --splunk-config aws` reads `terraform.aws` from the environment config. `aws` is the only legal value. Skills do not assemble `spa aws --validate` with region, AMI, key, security groups, and instance type when those values are already in the config. `spa aws --validate` remains the low-level command.
