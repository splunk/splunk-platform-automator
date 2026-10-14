#!/bin/sh
# Run splunk with credentials read from mode-0600 files.
# Ansible's command string stays free of those values; a failed task can
# still print splunk's stdout and stderr.
set -eu

splunk_home=""
auth_file=""
secret_file=""
password_file=""
remote_password_file=""
auth_user="admin"
no_auth=0
password_as_arg=0

while [ $# -gt 0 ]; do
  case "$1" in
    --splunk-home)
      splunk_home=$2
      shift 2
      ;;
    --auth-file)
      auth_file=$2
      shift 2
      ;;
    --secret-file)
      secret_file=$2
      shift 2
      ;;
    --password-file)
      password_file=$2
      shift 2
      ;;
    --remote-password-file)
      remote_password_file=$2
      shift 2
      ;;
    --auth-user)
      auth_user=$2
      shift 2
      ;;
    --no-auth)
      no_auth=1
      shift
      ;;
    --password-as-arg)
      password_as_arg=1
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "spa_splunk_cli: unexpected argument" >&2
      exit 2
      ;;
  esac
done

if [ -z "$splunk_home" ]; then
  echo "spa_splunk_cli: --splunk-home is required" >&2
  exit 2
fi

read_trimmed() {
  IFS= read -r value < "$1" || return 1
  printf '%s' "$value"
}

if [ "$password_as_arg" -eq 1 ]; then
  pw=$(read_trimmed "$auth_file")
  set -- "$@" "$pw"
  unset pw
fi
if [ -n "$secret_file" ]; then
  secret=$(read_trimmed "$secret_file")
  set -- "$@" -secret "$secret"
  unset secret
fi
if [ -n "$password_file" ]; then
  pw=$(read_trimmed "$password_file")
  set -- "$@" -password "$pw"
  unset pw
fi
if [ -n "$remote_password_file" ]; then
  remote_pw=$(read_trimmed "$remote_password_file")
  set -- "$@" -remoteUsername admin -remotePassword "$remote_pw"
  unset remote_pw
fi
if [ "$no_auth" -eq 0 ] && [ "$password_as_arg" -eq 0 ]; then
  auth=$(read_trimmed "$auth_file")
  set -- "$@" -auth "${auth_user}:${auth}"
  unset auth
fi

exec "$splunk_home/bin/splunk" "$@"
