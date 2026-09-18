import argparse
import json
import os
import subprocess
import sys


class ShellError(RuntimeError):
    """Inventory or host lookup failed (library path; CLI still may sys.exit)."""


def apply_spa_env():
    """Export SPA_HOME / SPA_ENV_DIR / ANSIBLE_* so inventory uses the env, not the clone."""
    from spa.executil import apply_paths_env
    from spa.paths import resolve_spa_paths

    apply_paths_env(resolve_spa_paths())



def get_inventory_data():
    """Retrieves inventory data from ansible-inventory."""
    try:
        from spa.executil import tool_path
        from spa.paths import resolve_spa_paths

        inventory_bin = tool_path(resolve_spa_paths(), "ansible-inventory")
        result = subprocess.run(
            [inventory_bin, "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
        # JSON should start with {
        if '{' in output:
             output = output[output.find('{'):]
        return json.loads(output)
    except subprocess.CalledProcessError as e:
        raise ShellError("Error running ansible-inventory: %s" % (e.stderr or e)) from e
    except FileNotFoundError as e:
        raise ShellError("Error: %s not found. Run: spa doctor" % (e.filename or "ansible-inventory")) from e
    except json.JSONDecodeError as e:
        raise ShellError("Error parsing inventory JSON: %s" % e) from e

def get_host_vars(inventory, hostname):
    """Finds variables for a specific host in the inventory."""
    # Check if host exists in _meta (common in dynamic inventory)
    if '_meta' in inventory and 'hostvars' in inventory['_meta']:
        if hostname in inventory['_meta']['hostvars']:
            return inventory['_meta']['hostvars'][hostname]
    
    return {}

def check_ansible_status(hosts, paths=None):
    """Checks Ansible connectivity for a list of hosts using ping."""
    status_map = {}
    if not hosts:
        return status_map

    import tempfile
    import shutil

    from spa.executil import ToolNotFound, tool_path
    from spa.paths import resolve_spa_paths

    # ansible lives in the spa venv, not necessarily on PATH (same as
    # ansible-inventory / ansible-playbook).
    try:
        ansible_bin = tool_path(paths or resolve_spa_paths(), "ansible")
    except ToolNotFound as exc:
        print("Warning: %s" % exc, file=sys.stderr)
        return status_map

    temp_dir = tempfile.mkdtemp(prefix='spash_ansible_')
    
    try:
        # Use --limit to rely on the inventory but restrict to specific hosts
        # hosts is a list of hostnames
        limit_pattern = ':'.join(hosts)
        
        # If list is too long, we might hit CLI limits, but for typical use reasonable.
        # Fallback to 'all' if empty or issues? No, if empty we returned above.
        
        cmd = [ansible_bin, 'all', '--limit', limit_pattern, '-m', 'ping', '--tree', temp_dir]
        
        print("Checking Ansible connectivity...", file=sys.stderr)
        # We don't care about stdout/stderr much, but capture to keep clean
        subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        # Read results from temp_dir
        if os.path.exists(temp_dir):
            for filename in os.listdir(temp_dir):
                host = filename
                filepath = os.path.join(temp_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        
                    # Structure: { "ping": "pong", ... } or { "unreachable": true, ... }
                    if data.get('unreachable'):
                        status_map[host] = 'Unreachable'
                    elif data.get('failed'):
                        status_map[host] = 'Failed'
                    elif data.get('ping') == 'pong':
                        status_map[host] = 'Success'
                    else:
                        status_map[host] = 'Unknown'
                except (json.JSONDecodeError, OSError):
                    status_map[host] = 'Error'
                    
    except FileNotFoundError:
        print(
            "Warning: %s not found. Repair it: spa venv --shared --rebuild --yes" % ansible_bin,
            file=sys.stderr,
        )
    except Exception as e:
        print(f"Error running ansible ping: {e}", file=sys.stderr)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    return status_map

def get_provider_status(paths=None):
    """Return provider status without coupling shell UX to a cloud SDK."""
    from spa.paths import resolve_spa_paths
    from spa.providers import ProviderError, get_provider

    paths = paths or resolve_spa_paths()
    try:
        provider = get_provider(paths)
    except ProviderError as exc:
        return {"name": None, "hosts": {}, "error": str(exc)}
    status_fn = getattr(provider, "host_status", None)
    if status_fn is None:
        return {
            "name": provider.name,
            "hosts": {},
            "error": "%s provider does not expose host status." % provider.name,
        }
    try:
        return {"name": provider.name, "hosts": status_fn(), "error": None}
    except ProviderError as exc:
        return {"name": provider.name, "hosts": {}, "error": str(exc)}


def _provider_record(host, inventory, provider_hosts):
    host_vars = get_host_vars(inventory, host)
    identifiers = (
        host,
        host_vars.get("ansible_host"),
        host_vars.get("public_dns_name"),
        host_vars.get("public_ip"),
        host_vars.get("private_dns_name"),
        host_vars.get("private_ip"),
        host_vars.get("instance_id"),
    )
    for identifier in identifiers:
        if identifier and str(identifier) in provider_hosts:
            return provider_hosts[str(identifier)]
    return None


def host_report(
    inventory, verbose=False, paths=None, provider_snapshot=None, runtime=True
):
    """Return hosts plus optional provider and Ansible runtime status."""
    hosts = set()
    if "_meta" in inventory and "hostvars" in inventory["_meta"]:
        hosts.update(inventory["_meta"]["hostvars"].keys())
    else:
        for group in inventory:
            if group == "_meta":
                continue
            if "hosts" in inventory[group]:
                hosts.update(inventory[group]["hosts"])

    hosts_sorted = sorted(list(hosts))
    ansible_status = {}
    provider = {"name": None, "hosts": {}, "error": None}
    if verbose and runtime:
        provider = provider_snapshot or get_provider_status(paths)
        provider_hosts = provider.get("hosts") or {}
        hosts_to_ping = []
        for host in hosts_sorted:
            record = _provider_record(host, inventory, provider_hosts)
            if record and record.get("reachable") is False:
                ansible_status[host] = "N/A"
            else:
                hosts_to_ping.append(host)
        if hosts_to_ping:
            ping_results = check_ansible_status(hosts_to_ping, paths=paths)
            ansible_status.update(ping_results)
    elif verbose:
        ansible_status = {host: "unprovisioned" for host in hosts_sorted}

    rows = []
    for host in hosts_sorted:
        roles = []
        for group in inventory:
            if group.startswith("role_"):
                if "hosts" in inventory[group] and host in inventory[group]["hosts"]:
                    role_name = group[5:].replace("_", " ").title()
                    roles.append(role_name)
        roles.sort()
        row = {"name": host, "roles": roles}
        if verbose:
            row["ansible"] = ansible_status.get(host, "N/A")
            if not runtime:
                row["provider_status"] = "unprovisioned"
            else:
                record = _provider_record(host, inventory, provider.get("hosts") or {})
                if record:
                    row["provider"] = provider.get("name")
                    row["provider_status"] = record.get("state")
        rows.append(row)
    return {
        "provider": provider.get("name"),
        "provider_error": provider.get("error"),
        "hosts": rows,
    }


def host_listing(inventory, verbose=False, paths=None, provider_snapshot=None):
    """Return structured host rows (compatibility wrapper)."""
    return host_report(
        inventory,
        verbose=verbose,
        paths=paths,
        provider_snapshot=provider_snapshot,
    )["hosts"]


def filter_report(report, names):
    """Keep only named hosts in a host_report payload."""
    if not names:
        return report
    wanted = set(names)
    filtered = dict(report)
    filtered["hosts"] = [row for row in report.get("hosts") or [] if row.get("name") in wanted]
    filtered["resolved_hosts"] = list(names)
    return filtered


def format_host_status(row):
    """Human suffix for spa hosts list --status."""
    if row.get("ansible") == "unprovisioned" or row.get("provider_status") == "unprovisioned":
        return " - unprovisioned"
    provider_status = ""
    if row.get("provider_status"):
        provider_status = ", %s: %s" % (
            str(row.get("provider") or "provider").upper(),
            row["provider_status"],
        )
    if row.get("ansible") or row.get("provider_status"):
        return " - Ansible: %s%s" % (row.get("ansible", "N/A"), provider_status)
    return ""


def list_hosts(inventory, verbose=False, paths=None, names=None):
    """Lists all hosts in the inventory with their roles."""
    report = filter_report(
        host_report(inventory, verbose=verbose, paths=paths),
        names,
    )
    if verbose and report.get("provider"):
        print("Checking %s status..." % report["provider"].upper(), file=sys.stderr)
    if verbose and report.get("provider_error"):
        print("Warning: %s" % report["provider_error"], file=sys.stderr)
    for row in report["hosts"]:
        roles_str = ""
        if row.get("roles"):
            roles_str = " (%s)" % ", ".join(row["roles"])
        extra_info = ""
        if verbose:
            extra_info = format_host_status(row)
        print("%s%s%s" % (row["name"], roles_str, extra_info))

def resolve_connection_details(target_host, inventory):
    """Resolves a target host alias to connection details."""
    host_vars = get_host_vars(inventory, target_host)
    if not host_vars:
        return None

    # Resolve connection details
    # Priority: ansible_host > public_dns_name > target_host
    real_host = host_vars.get('ansible_host') or host_vars.get('public_dns_name') or target_host
    
    # User resolution
    # Priority: ansible_user
    user = host_vars.get('ansible_user')

    # Key resolution
    # Priority: ansible_ssh_private_key_file
    key_file = host_vars.get('ansible_ssh_private_key_file')

    if key_file:
         # Expand user path for key file
         key_file = os.path.expanduser(key_file)
    
    # Proxy (Jump Host)
    ssh_common_args = host_vars.get('ansible_ssh_common_args', '')
    
    return {
        'real_host': real_host,
        'user': user,
        'key_file': key_file,
        'ssh_common_args': ssh_common_args
    }

COPY_EXAMPLES = """Path syntax:
  HOST:PATH   a path on an env host, using the inventory name (idx1:/tmp/)
  PATH        a path on this machine

Examples:
  spa hosts copy app.tgz idx1:/tmp/
  spa hosts copy idx1:/opt/splunk/etc/system/local/server.conf .
  spa hosts copy cm:/opt/splunk/var/log/splunk/splunkd.log ./cm-splunkd.log
  spa hosts copy -r ./myapp idx1:/tmp/
  spa hosts copy -- -p app.tgz idx1:/tmp/         (other scp flags after --)

Names come from spa hosts list; user and SSH key come from the inventory.
One remote host per run; repeat the command for the next host."""


def run_scp(cmd_args, inventory=None):
    """Exec scp, resolving HOST:PATH against inventory. scp flags may lead."""
    if inventory is None:
        inventory = get_inventory_data()
    all_hosts = []
    if '_meta' in inventory and 'hostvars' in inventory['_meta']:
        all_hosts = list(inventory['_meta']['hostvars'].keys())

    scp_cmd = ['scp']
    resolved_details = None
    processed_args = []
    options = []

    for arg in cmd_args:
        # Simple heuristic for remote path: has colon and starts with a known host
        if ':' in arg:
            parts = arg.split(':', 1)
            candidate_host = parts[0]
            path = parts[1]

            if candidate_host in all_hosts:
                if not resolved_details:
                    resolved_details = resolve_connection_details(candidate_host, inventory)

                if resolved_details:
                    # Replace alias with real connection string
                    # user@host:path
                    remote_str = resolved_details['real_host']
                    if resolved_details['user']:
                        remote_str = f"{resolved_details['user']}@{remote_str}"
                    processed_args.append(f"{remote_str}:{path}")
                    continue
        # scp uses getopt: its own flags must come before the paths.
        if arg.startswith('-') and not processed_args:
            options.append(arg)
            continue

        processed_args.append(arg)

    # Build scp command
    if resolved_details:
        if resolved_details['key_file']:
            if os.path.exists(resolved_details['key_file']):
                scp_cmd.extend(['-i', resolved_details['key_file']])
            else:
                print(f"Warning: Private key file '{resolved_details['key_file']}' not found.", file=sys.stderr)

        if resolved_details['ssh_common_args']:
            scp_cmd.extend(resolved_details['ssh_common_args'].split())

    # Add strict host key checking=no for convenience
    scp_cmd.extend(['-o', 'StrictHostKeyChecking=no'])
    scp_cmd.extend(['-o', 'UserKnownHostsFile=/dev/null'])

    scp_cmd.extend(options)
    scp_cmd.extend(processed_args)

    print(f"Copying: {' '.join(scp_cmd)}")
    os.execvp('scp', scp_cmd)


def main(argv=None):
    apply_spa_env()

    parser = argparse.ArgumentParser(
        prog="spa shell",
        description="SSH or SCP using inventory (alias of spa hosts ssh / spa hosts copy).",
        epilog="Copy: spa shell -c SRC DST, where a remote side is HOST:PATH\n"
        "  spa shell -c app.tgz idx1:/tmp/\n"
        "  spa shell -c idx1:/opt/splunk/etc/system/local/server.conf .\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("host", nargs='?', help="Inventory hostname to SSH to, or first scp path with -c")
    parser.add_argument("-c", "--copy", action="store_true", help="Use scp to copy files (SRC DST)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Additional arguments to pass to ssh/scp")
    args = parser.parse_args(argv)

    if not args.host:
        parser.print_help()
        sys.exit(1)

    try:
        inventory = get_inventory_data()
    except ShellError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    
    # Check if host is known
    all_hosts = []
    if '_meta' in inventory and 'hostvars' in inventory['_meta']:
        all_hosts = list(inventory['_meta']['hostvars'].keys())

    if args.copy:
        cmd_args = [args.host, *(args.args or [])]
        if len(cmd_args) < 2:
            print(
                "spa shell -c needs a source and a destination, "
                "for example: spa shell -c app.tgz idx1:/tmp/",
                file=sys.stderr,
            )
            sys.exit(1)
        run_scp(cmd_args, inventory)

    else:
        # SSH Mode
        target_host = args.host
        extra_args = args.args
    
        if target_host not in all_hosts:
            print(f"Error: Host '{target_host}' not found in inventory.", file=sys.stderr)
            matches = [h for h in all_hosts if target_host in h]
            if matches:
                print(f"Did you mean: {', '.join(matches)}?", file=sys.stderr)
            sys.exit(1)

        details = resolve_connection_details(target_host, inventory)
        
        # Construct SSH command
        ssh_cmd = ['ssh']
        
        if details['key_file']:
            if os.path.exists(details['key_file']):
                ssh_cmd.extend(['-i', details['key_file']])
            else:
                 print(f"Warning: Private key file '{details['key_file']}' not found.", file=sys.stderr)

        if details['user']:
            ssh_cmd.extend(['-l', details['user']])

        if details['ssh_common_args']:
             ssh_cmd.extend(details['ssh_common_args'].split())

        # Add strict host key checking=no for convenience
        ssh_cmd.extend(['-o', 'StrictHostKeyChecking=no'])
        ssh_cmd.extend(['-o', 'UserKnownHostsFile=/dev/null'])

        ssh_cmd.append(details['real_host'])

        if extra_args:
            ssh_cmd.extend(extra_args)

        as_user = f" as {details['user']}" if details["user"] else ""
        print(f"Connecting to {target_host} ({details['real_host']}){as_user}...")
        
        # Replace current process with ssh
        os.execvp('ssh', ssh_cmd)

