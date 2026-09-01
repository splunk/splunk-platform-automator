# Secrets handling (mandatory)

**Never display credential values** in chat, terminal output shown to the user, plan files, or config comments — including values read from environment variables.

Applies to the full `spa-create-config` workflow (plan and write modes).

## Splunkbase (app deployment phase)

| Variable | In YAML config | In chat / terminal |
|----------|----------------|-------------------|
| `SPLUNKBASE_USERNAME` | `{{ lookup('env', 'SPLUNKBASE_USERNAME') }}` only | Report **set** or **not set** — never the email/username |
| `SPLUNKBASE_PASSWORD` | `{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}` only | Report **set** or **not set** — never the password |

Do **not** paste resolved lookup results if a command or playbook prints them.

## AWS API credentials (Phase 4 / validate)

Used by `splunk_config_aws.py`, Terraform provision, and optional `--splunk-config-aws`.

| Variable / item | Show in chat? | Notes |
|-----------------|---------------|-------|
| `AWS_ACCESS_KEY_ID` | **Never** the value | Report **set** or **not set** only |
| `AWS_SECRET_ACCESS_KEY` | **Never** | Report **set** or **not set** only |
| `AWS_SESSION_TOKEN` | **Never** (temporary creds) | Report **set** or **not set** only |
| `AWS_PROFILE` | **OK** — profile name is not a secret | e.g. `AWS_PROFILE: my-dev-profile` |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | **OK** | e.g. `eu-central-1` |
| Account ID from `--check-auth` | **OK** | 12-digit account ID |
| ARN from `--check-auth` | **OK** | Contains account ID, not the secret key |
| `ssh_private_key_file` path in config | **OK** | Path only — **never** key file contents |

**Preferred AWS check** (no env echo):

```bash
python3 bin/splunk_config_aws.py --check-auth --json
```

Report: *AWS API: ok (account 123456789012)* or *AWS API: failed — credentials not available* — not raw env vars.

If `--check-auth` is inconclusive, use set/not-set loops below — not `echo` / `printenv`.

## Other secrets — same rule

Never show values for: private key file contents, license file contents, or inline passwords in `splunk_config.yml`.

## Forbidden verification commands

Do not run or suggest:

**Splunkbase**

- `echo $SPLUNKBASE_USERNAME` / `echo $SPLUNKBASE_PASSWORD`
- `printenv SPLUNKBASE_*` / `env | grep SPLUNKBASE`
- `python -c "... os.environ['SPLUNKBASE_PASSWORD'] ..."`

**AWS**

- `echo $AWS_ACCESS_KEY_ID` / `echo $AWS_SECRET_ACCESS_KEY` / `echo $AWS_SESSION_TOKEN`
- `printenv AWS_*` / `env | grep AWS_` (leaks secrets mixed with safe vars)
- `aws configure get aws_secret_access_key` / `aws configure list` (shows secret key in output)
- `cat` / `head` on `~/.aws/credentials`

Any command that prints secret env values or credential file contents to stdout.

## Safe presence checks (optional)

**Splunkbase** — from project root:

```bash
for v in SPLUNKBASE_USERNAME SPLUNKBASE_PASSWORD; do
  if [ -n "${!v:-}" ]; then echo "$v: set"; else echo "$v: not set"; fi
done
```

**AWS static keys** (when not using profile-only auth):

```bash
for v in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN; do
  if [ -n "${!v:-}" ]; then echo "$v: set"; else echo "$v: not set"; fi
done
```

If `AWS_PROFILE` is set, report the profile name; still prefer `--check-auth` for “will API calls work?”

Report summaries without values — e.g. *AWS: profile `lab`; static key env vars not set; `--check-auth` ok*.

## YAML snippets in chat

Use lookup templates from examples — never substitute live env values into snippets or architecture plans.

## If credentials missing

- Splunkbase: [docs/App_Deployment.md](docs/App_Deployment.md) — user exports locally; do not ask them to paste passwords in chat.
- AWS: [aws-without-credentials.md](aws-without-credentials.md) — static AMI fallback; user configures profile or env before provision.
