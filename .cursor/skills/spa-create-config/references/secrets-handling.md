# Secrets handling (mandatory)

**Never display credential values** in chat, terminal output shown to the user, plan files, or config comments — including values read from environment variables.

Applies to the full `spa-create-config` workflow (plan and write modes).

## Splunkbase (most common during this skill)

| Variable | In YAML config | In chat / terminal |
|----------|----------------|-------------------|
| `SPLUNKBASE_USERNAME` | `{{ lookup('env', 'SPLUNKBASE_USERNAME') }}` only | Report **set** or **not set** — never the email/username |
| `SPLUNKBASE_PASSWORD` | `{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}` only | Report **set** or **not set** — never the password |

Do **not** paste resolved lookup results if a command or playbook prints them.

## Other secrets — same rule

Never show values for: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, private key file contents, license file contents, or inline passwords in `splunk_config.yml`.

AWS `--check-auth` may return `account` (12-digit account ID) — that is OK; do not echo access keys.

## Forbidden verification commands

Do not run or suggest:

- `echo $SPLUNKBASE_USERNAME` / `echo $SPLUNKBASE_PASSWORD`
- `printenv SPLUNKBASE_*` / `env | grep SPLUNKBASE`
- `python -c "... os.environ['SPLUNKBASE_PASSWORD'] ..."`
- Any command that prints secret env values to stdout

## Safe presence check (optional)

From project root, only when user needs credential status:

```bash
for v in SPLUNKBASE_USERNAME SPLUNKBASE_PASSWORD; do
  if [ -n "${!v:-}" ]; then echo "$v: set"; else echo "$v: not set"; fi
done
```

Report summary to user: e.g. *Splunkbase credentials: both set* — no values.

## YAML snippets in chat

Use the lookup template from examples — never substitute live env values into snippets or architecture plans.

## If credentials missing

Tell the user to export vars locally (see [docs/App_Deployment.md](docs/App_Deployment.md)) without asking them to paste passwords in chat.
