"""Human bash and zsh completion. One candidate provider, no embedded schema."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

COMPLETION_NEEDS_SHELL = (
    "spa completion needs a shell.\n"
    "Bash: spa completion bash\n"
    "Zsh:  spa completion zsh"
)
COMPLETION_AGENT = (
    "spa completion is for a human shell, not an agent.\n"
    "Agents discover commands with: spa agent schema\n"
    "Bash: spa completion bash\n"
    "Zsh:  spa completion zsh"
)
INSTALL_PAGE = """\
Print a bash or zsh completion function. spa does not edit ~/.bashrc or ~/.zshrc.

zsh runs compinit before the function is loaded:

  autoload -Uz compinit && compinit

Load completions for this session:

  eval "$(spa --no-agent completion zsh)"
  eval "$(spa --no-agent completion bash)"

Load them for every new session. Add the eval line to ~/.zshrc or ~/.bashrc,
after compinit. spa does not edit those files.

  echo 'eval "$(spa --no-agent completion zsh)"' >> ~/.zshrc
  echo 'eval "$(spa --no-agent completion bash)"' >> ~/.bashrc

Or save a static file. zsh needs the directory on fpath before compinit:

  mkdir -p ~/.zsh/completions
  echo 'fpath=(~/.zsh/completions $fpath)' >> ~/.zshrc
  spa --no-agent completion zsh > ~/.zsh/completions/_spa
  mkdir -p ~/.local/share/bash-completion/completions
  spa --no-agent completion bash > ~/.local/share/bash-completion/completions/spa

The bash file is read by bash-completion 2.

Fish and PowerShell are not supported. Agents use spa agent schema, not shell completion.
"""

_BASH = """\
# bash completion for spa
_spa_completion() {
  local reply candidate
  if [[ ${COMP_CWORD:-0} -gt 0 && ${COMP_WORDS[COMP_CWORD-1]} == --start-dir ]]; then
    COMPREPLY=()
    while IFS= read -r candidate; do
      [[ -n "$candidate" ]] && COMPREPLY+=("$candidate")
    done < <(compgen -d -- "${COMP_WORDS[COMP_CWORD]}")
    return 0
  fi
  local IFS=$'\\n'
  COMPREPLY=()
  reply="$(spa --no-agent completion -- line "$COMP_POINT" "$COMP_LINE")" || return 0
  if [[ -z "$reply" ]]; then
    return 0
  fi
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] && COMPREPLY+=("$candidate")
  done <<< "$reply"
}
complete -o default -F _spa_completion spa
"""

_ZSH = """\
#compdef spa
_spa() {
  if [[ ${words[CURRENT-1]} == --start-dir ]]; then
    _files -/
    return
  fi
  local -a candidates
  candidates=(${(f)"$(spa --no-agent completion -- "$((CURRENT - 1))" "${words[@]}")"})
  compadd -a candidates
}

if [[ "${funcstack[1]-}" == _spa ]]; then
  _spa
elif (( $+functions[compdef] )); then
  compdef _spa spa
fi
"""

_BOOLEAN = frozenset(
    {
        "--yes",
        "--dry-run",
        "--explicit-default",
        "--full",
        "--effective",
        "--markdown",
        "--status",
        "--force",
        "--shared",
        "--all",
        "--extract",
        "--overwrite",
        "--no-install",
        "--no-wait",
        "--ansible-output",
        "--timestamps",
        "--color",
        "--export",
        "--follow",
        "--last",
        "--json",
        "--local",
        "--customize",
        "--verbose",
        "--agent",
        "--no-agent",
        "-y",
        "-s",
        "-v",
    }
)
_ROOT_BOOL = ("--agent", "--no-agent", "--json", "--yes", "-y", "--verbose", "-v")
_GLOBAL_VALUE = frozenset({"--env", "--start-dir"})
_PATH_COMMANDS = frozenset({"config explain", "config search", "config get", "config set"})
_SELECTOR = re.compile(r"^splunk_hosts\[name=([^[\]]+)\](.*)$")


def words_from_line(line: str, point: int) -> Tuple[List[str], int]:
    """Split a raw command line the way a human typed it, cursor included."""
    import shlex

    point = max(0, min(int(point), len(line)))
    before = line[:point]
    try:
        tokens = shlex.split(before, posix=True)
    except ValueError:
        tokens = before.split()
    if not before or before[-1].isspace():
        tokens.append("")
    if not tokens:
        tokens = [""]
    return tokens, len(tokens) - 1


def completion_script(shell: str) -> str:
    """Return the bash or zsh function. ``shell`` is ``bash`` or ``zsh``."""
    if shell == "bash":
        return _BASH
    if shell == "zsh":
        return _ZSH
    raise ValueError(shell)


def complete(
    words: Sequence[str],
    index: int,
    config: Optional[Mapping[str, Any]] = None,
    paths: Any = None,
) -> List[str]:
    """Candidates for ``words[index]``. ``config`` is the local splunk_config.yml mapping."""
    words = [str(item) for item in words]
    if index < 0:
        index = 0
    if index > len(words):
        index = len(words)
    current = words[index] if index < len(words) else ""
    command, rest = _split(words, index)
    entry = _entry(command)
    flag = _open_flag(entry, rest)
    if flag is not None:
        return _flag_values(flag, current, config, paths)
    if current.startswith("-"):
        return _filter(_flag_names(entry), current)
    if command == "config keys":
        return []
    if command == "config set" and _secret_value(rest):
        return []
    found: List[str] = []
    if not _positionals(entry, rest):
        found.extend(_next_words(command))
    slot = _open_positional(entry, rest)
    if slot is not None:
        if slot.get("choices"):
            found.extend(str(item) for item in slot["choices"])
        if slot.get("completes_from"):
            found.extend(_catalog(str(slot["completes_from"]), config, paths))
    if command in _PATH_COMMANDS and _on_path(entry, rest):
        found.extend(_config_paths(current, config))
    return _filter(found, current)


def _schema() -> List[Dict[str, Any]]:
    from spa.agent import COMMAND_SCHEMA

    return list(COMMAND_SCHEMA.get("commands") or [])


def _by_name() -> Dict[str, Dict[str, Any]]:
    return {str(row.get("name") or ""): row for row in _schema()}


def _entry(name: str) -> Dict[str, Any]:
    rows = _by_name()
    if name == "init":
        return _merged(rows.get("init") or {"name": "init"}, rows.get("environment init") or {})
    if name == "shell":
        base = dict(rows.get("shell") or {"name": "shell"})
        base.setdefault(
            "positionals",
            [{"name": "NAME", "required": False, "completes_from": "hosts"}],
        )
        return base
    return rows.get(name) or {"name": name}


def _merged(left: Mapping[str, Any], right: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(left)
    flags = list(left.get("flags") or []) + list(right.get("flags") or [])
    if flags:
        out["flags"] = flags
    if not out.get("positionals") and right.get("positionals"):
        out["positionals"] = list(right["positionals"])
    return out


def _aliases() -> Tuple[Dict[Tuple[str, ...], Dict[str, str]], Dict[str, Any]]:
    from spa.cli import _HIDDEN_ALIASES, _VISIBLE_ALIAS

    return _HIDDEN_ALIASES, _VISIBLE_ALIAS


def _canonical(parts: Sequence[str], token: str) -> str:
    hidden, visible = _aliases()
    mapped = hidden.get(tuple(parts), {}).get(token, token)
    if not parts and token == "env":
        mapped = "environment"
    if not parts and token in (visible.get("environment") or ()):
        mapped = "environment"
    return mapped


def _extends(parts: Sequence[str], token: str) -> bool:
    prefix = " ".join([*parts, token])
    for name in _by_name():
        if name == prefix or name.startswith(prefix + " "):
            return True
    return False


def _global_kind(token: str) -> str:
    """``value`` or ``bool`` for a flag that can precede the command."""
    if token in _GLOBAL_VALUE:
        return "value"
    if token in _ROOT_BOOL or (token.startswith("-v") and set(token[1:]) <= {"v"}):
        return "bool"
    return ""


def _split(words: Sequence[str], index: int) -> Tuple[str, List[str]]:
    start = 1 if words and _is_spa(words[0]) and index > 0 else 0
    parts: List[str] = []
    i = start
    while i < index:
        token = words[i]
        kind = _global_kind(token)
        if kind == "value":
            if i + 1 >= index:
                break
            i += 2
            continue
        if kind == "bool":
            i += 1
            continue
        if token.startswith("-"):
            break
        canon = _canonical(parts, token)
        if _extends(parts, canon):
            parts.append(canon)
            i += 1
            continue
        break
    name = ""
    for length in range(len(parts), 0, -1):
        candidate = " ".join(parts[:length])
        if candidate in _by_name():
            name = candidate
            break
    return name, list(words[i:index])


def _is_spa(token: str) -> bool:
    return token == "spa" or token.endswith("/spa")


def _takes_value(flag: Mapping[str, Any]) -> bool:
    if "takes_value" in flag:
        return bool(flag["takes_value"])
    if flag.get("choices") or flag.get("completes_from"):
        return True
    long = str(flag.get("long") or "")
    short = str(flag.get("short") or "")
    return long not in _BOOLEAN and short not in _BOOLEAN


def _flags(entry: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    rows = list(entry.get("flags") or [])
    rows.extend(
        {
            "long": name,
            "takes_value": True,
            "completes_from": "environment list" if name == "--env" else "",
        }
        for name in ("--env", "--start-dir")
    )
    return rows


def _spec(entry: Mapping[str, Any], token: str) -> Optional[Mapping[str, Any]]:
    for flag in _flags(entry):
        if token in {flag.get("long"), flag.get("short")} and token:
            return flag
    return None


def _open_flag(entry: Mapping[str, Any], rest: Sequence[str]) -> Optional[Mapping[str, Any]]:
    if not rest:
        return None
    spec = _spec(entry, rest[-1])
    if spec is not None and _takes_value(spec):
        return spec
    return None


def _positionals(entry: Mapping[str, Any], rest: Sequence[str]) -> List[str]:
    found: List[str] = []
    index = 0
    while index < len(rest):
        spec = _spec(entry, rest[index])
        if spec is not None:
            index += 2 if _takes_value(spec) else 1
            continue
        found.append(rest[index])
        index += 1
    return found


def _open_positional(entry: Mapping[str, Any], rest: Sequence[str]) -> Optional[Mapping[str, Any]]:
    slots = list(entry.get("positionals") or [])
    used = _positionals(entry, rest)
    if len(used) < len(slots):
        return slots[len(used)]
    return None


def _on_path(entry: Mapping[str, Any], rest: Sequence[str]) -> bool:
    if _open_flag(entry, rest) is not None:
        return False
    return len(_positionals(entry, rest)) == 0


def _secret_value(rest: Sequence[str]) -> bool:
    from spa.config_edit import _is_secret

    positional = [token for token in rest if not token.startswith("-")]
    return len(positional) == 1 and _is_secret(positional[0])


def _flag_names(entry: Mapping[str, Any]) -> List[str]:
    names = list(_ROOT_BOOL)
    names.extend(["--env", "--start-dir"])
    for flag in entry.get("flags") or []:
        if flag.get("long"):
            names.append(str(flag["long"]))
        if flag.get("short"):
            names.append(str(flag["short"]))
    return names


def _flag_values(
    flag: Mapping[str, Any],
    current: str,
    config: Optional[Mapping[str, Any]],
    paths: Any,
) -> List[str]:
    long = str(flag.get("long") or "")
    if long in {"--from-env", "--start-dir"}:
        return []
    if long == "--hosts" or flag.get("completes_from") == "hosts":
        return _filter(_hosts(config, ""), current)
    if flag.get("choices"):
        return _filter([str(item) for item in flag["choices"]], current)
    kind = str(flag.get("completes_from") or "")
    if kind:
        return _filter(_catalog(kind, config, paths), current)
    if long == "--provider":
        return _filter(_catalog("providers", config, paths), current)
    if long == "--example":
        return _filter(_catalog("init list", config, paths), current)
    return []


def _next_words(command: str) -> List[str]:
    prefix = command + " " if command else ""
    found = []
    for name in _by_name():
        if prefix and not name.startswith(prefix):
            continue
        rest = name[len(prefix):]
        segment = rest.split(" ", 1)[0]
        if segment and segment != command:
            found.append(segment)
    return found


def _filter(items: Iterable[str], prefix: str) -> List[str]:
    prefix = prefix or ""
    return sorted({item for item in items if item.startswith(prefix) and "[]" not in item})


def _hosts(config: Optional[Mapping[str, Any]], prefix: str) -> List[str]:
    if not config:
        return []
    from spa.providers import expected_hostnames

    names = list(expected_hostnames(dict(config)))
    roles: List[str] = []
    for host in config.get("splunk_hosts") or []:
        if isinstance(host, dict):
            roles.extend(str(role) for role in host.get("roles") or [])
    return _filter([*names, *roles], prefix)


def _config_paths(token: str, config: Optional[Mapping[str, Any]]) -> List[str]:
    from spa.config_tree import explain_candidates

    match = _SELECTOR.match(token or "")
    if match:
        name, rest = match.group(1), match.group(2)
        query = "splunk_hosts" + (rest if rest else "")
        if rest in {"", "."}:
            query = "splunk_hosts." if rest == "." else "splunk_hosts"
        prefix = "splunk_hosts[name=%s]" % name
        rewritten = []
        for child in explain_candidates(query):
            if child.startswith("splunk_hosts"):
                rewritten.append(prefix + child[len("splunk_hosts"):])
        return rewritten
    found = list(explain_candidates(token))
    if config and (not token or token.startswith("splunk_h") or "splunk_hosts".startswith(token)):
        from spa.providers import expected_hostnames

        for host in expected_hostnames(dict(config)):
            found.append("splunk_hosts[name=%s]" % host)
    return found


def _catalog(kind: str, config: Optional[Mapping[str, Any]], paths: Any) -> List[str]:
    try:
        return _catalog_values(kind, config, paths)
    except Exception:
        return []


def _catalog_values(kind: str, config: Optional[Mapping[str, Any]], paths: Any) -> List[str]:
    if kind == "hosts":
        return _hosts(config, "")
    if kind in {"init list", "providers"}:
        from spa.init import list_examples

        data = list_examples(_home(paths))
        key = "providers" if kind == "providers" else "topologies"
        values = [str(item.get("id")) for item in data.get(key) or [] if item.get("id")]
        if kind == "providers":
            values.extend(["aws", "external", "virtualbox"])
        return values
    if kind == "run list":
        from spa.paths import resolve_spa_paths
        from spa.playbooks import catalog

        rows = catalog(paths or resolve_spa_paths())
        return [str(row.get("name")) for row in rows if row.get("name")]
    if kind == "apps playbooks":
        from spa.app_playbooks import list_app_playbooks

        stems = []
        for row in list_app_playbooks(_home(paths)):
            file_name = str(row.get("file") or "")
            stem = Path(file_name).stem if file_name else str(row.get("name") or "")
            if stem:
                stems.append(stem)
        return stems
    if kind == "environment list":
        from spa.registry import list_environments

        return [str(row.get("name")) for row in list_environments() if row.get("name")]
    if kind == "logs list":
        from spa.paths import resolve_spa_paths
        from spa.runlog import list_runs

        rows = list_runs(paths or resolve_spa_paths())
        return [str(row.get("run_id")) for row in rows if row.get("run_id")]
    if kind == "config templates":
        from spa.config_edit import config_templates

        data = config_templates(_home(paths))
        return [str(row.get("name")) for row in data.get("templates") or [] if row.get("name")]
    if kind == "skills platforms":
        from spa.skills import PLATFORMS

        return [spec.name for spec in PLATFORMS] + ["all"]
    return []


def _home(paths: Any) -> Path:
    if paths is not None and getattr(paths, "spa_home", None):
        return Path(paths.spa_home)
    return Path(__file__).resolve().parents[2]
