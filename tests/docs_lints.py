"""Standing docs/skill lints: spa command schema, secrets, and CI comparisons."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Iterable, Mapping

import yaml

from spa.completion import (
    _ROOT_BOOL,
    _by_name,
    _canonical,
    _entry,
    _flags,
    _next_words,
    _takes_value,
)
from spa_testutil import PROJECT_ROOT

SHELL_FENCE_LANGS = frozenset({"", "bash", "sh", "shell", "zsh"})
SKIP_FENCE_LANGS = frozenset(
    {
        "mermaid",
        "json",
        "yaml",
        "yml",
        "python",
        "py",
        "text",
        "html",
        "javascript",
        "js",
        "diff",
        "xml",
        "toml",
        "jinja",
    }
)
FENCE = re.compile(r"^```([^\n]*)\n(.*?)(?:^```)", re.MULTILINE | re.DOTALL)
INLINE = re.compile(r"`([^`]+)`")
PLACEHOLDER_TOKEN = re.compile(r"^<[^>]+>$|^[A-Z][A-Z0-9_]*$")
COMMAND_WORD = re.compile(r"^[a-z][a-z0-9-]*$")
SPA_CLI_MARKEXPR = re.compile(r"SPA_CLI_MARKEXPR='([^']+)'")
SPA_ANSIBLE_MARKEXPR = re.compile(r"SPA_ANSIBLE_MARKEXPR='([^']+)'")
PYTEST_M = re.compile(r"""pytest\s+-m\s+['"]([^'"]+)['"]""")
RUNNER_MARKEXPR = {
    "run_ansible_tests.sh": "local and ansible",
    "run_unit_tests.sh": "local and not cli and not ansible",
    "run_local_tests.sh": "local",
}
AWS_DISCOVERY = frozenset(
    {
        "provider aws latest-ami",
        "provider aws survey",
        "provider aws describe-ami",
        "provider aws amis list",
    }
)
SECRET_TOKEN = re.compile(
    r"-----BEGIN [A-Z][A-Z0-9 ]*-----|AKIA|ghp_|sk_live_|sk_test_|eyJ[^\s.]*\.[^\s.]+\.[^\s.]+"
)
CREDENTIAL_KEY = re.compile(
    r"\b(password|secret|token|private[_-]?key|credential)\b", re.IGNORECASE
)
LOOKUP_ENV = re.compile(r"lookup\(\s*'env'", re.IGNORECASE)
VERBOSE_FLAG = re.compile(r"^(?:-v+|--verbose)$")
REQUIRED_CHECKS_SENTENCE = re.compile(
    r"requires the status checks\s+((?:[^`.]|`[^`]*`)+?)(?:\s+\(shown as|\.)",
    re.IGNORECASE | re.DOTALL,
)
BACKTICK_NAME = re.compile(r"`([^`]+)`")
GLOBAL_FLAGS = frozenset(_ROOT_BOOL) | {"--env", "--start-dir", "--help", "-h", "--version"}
GLOBAL_VALUE_FLAGS = frozenset({"--env", "--start-dir"})


def operator_doc_paths() -> list[Path]:
    """Markdown an operator or agent reads for spa commands (not CHANGELOG/ROADMAP)."""
    paths = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "AGENTS.md"]
    paths.extend(sorted((PROJECT_ROOT / "docs").glob("*.md")))
    paths.extend(sorted((PROJECT_ROOT / "skills").rglob("*.md")))
    agent = PROJECT_ROOT / ".agent"
    if agent.is_dir():
        paths.extend(sorted(agent.rglob("*.md")))
    tests_readme = PROJECT_ROOT / "tests" / "README.md"
    if tests_readme.is_file():
        paths.append(tests_readme)
    return [path for path in paths if path.is_file()]


def docs_and_skill_paths() -> list[Path]:
    """Operator docs plus skills for the secret scan (same set as the command lint)."""
    return operator_doc_paths()


def _fence_lang(info: str) -> str:
    token = (info or "").strip().split()[0].lower() if info.strip() else ""
    return token.split("{", 1)[0]


def _looks_like_spa(text: str) -> bool:
    stripped = text.strip().lstrip("$").strip()
    if not stripped:
        return False
    first = stripped.split(None, 1)[0]
    return first == "spa" or first.endswith("/spa")


def extract_spa_commands(text: str) -> list[tuple[int, str]]:
    """Fenced shell blocks and inline code only.

    Skip placeholders as command *lines* when the span is not a spa invocation;
    skip $-prompts, continuation-only lines, and alternative lists (`a` / `b`).
    Continuation backslashes inside a fence are joined into one command.
    """
    found: list[tuple[int, str]] = []
    claimed: set[int] = set()
    for match in FENCE.finditer(text):
        lang = _fence_lang(match.group(1))
        if lang in SKIP_FENCE_LANGS:
            continue
        if lang not in SHELL_FENCE_LANGS:
            continue
        body = match.group(2)
        start_line = text.count("\n", 0, match.start()) + 2
        joined: list[str] = []
        join_start = start_line
        for offset, raw in enumerate(body.splitlines()):
            line_no = start_line + offset
            claimed.add(line_no)
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                if joined and not joined[-1].endswith("\\"):
                    _flush_joined(found, join_start, joined)
                    joined = []
                continue
            if stripped.startswith("$"):
                continue
            if joined:
                joined.append(stripped)
            elif _looks_like_spa(stripped):
                join_start = line_no
                joined = [stripped]
            else:
                continue
            if stripped.endswith("\\"):
                continue
            _flush_joined(found, join_start, joined)
            joined = []
        if joined:
            _flush_joined(found, join_start, joined)

    for match in INLINE.finditer(text):
        span = match.group(1).strip()
        line_no = text.count("\n", 0, match.start()) + 1
        if line_no in claimed:
            continue
        if " / " in span or "\n" in span:
            continue
        if span.startswith("$"):
            continue
        if not _looks_like_spa(span):
            inner = re.search(r"\$\((spa\b[^)]*)\)", span)
            if inner is None:
                continue
            span = inner.group(1).strip()
        found.append((line_no, _strip_prompt(span)))
    return found


def _strip_prompt(line: str) -> str:
    text = " ".join(part.rstrip("\\").strip() for part in line.splitlines())
    return text.lstrip("$").strip()


def _flush_joined(found: list[tuple[int, str]], line_no: int, parts: list[str]) -> None:
    command = _strip_prompt(" ".join(parts))
    if command:
        found.append((line_no, command))


def _is_placeholder(token: str) -> bool:
    return bool(PLACEHOLDER_TOKEN.match(token))


def _schema_flags(name: str) -> dict[str, Mapping]:
    entry = _entry(name)
    by_token: dict[str, Mapping] = {}
    for flag in _flags(entry):
        for key in ("long", "short"):
            token = flag.get(key)
            if token:
                by_token[str(token)] = flag
    for token in GLOBAL_FLAGS:
        by_token.setdefault(token, {"long": token, "takes_value": token in GLOBAL_VALUE_FLAGS})
    return by_token


def _example_accepts_name(entry: Mapping, name: str) -> bool:
    if entry.get("positionals"):
        return True
    example = str(entry.get("example") or "")
    try:
        words = shlex.split(example)
    except ValueError:
        return False
    prefix = ["spa", *name.split()]
    index = 0
    for token in words:
        if index < len(prefix) and token in {prefix[index], "--agent", "--no-agent", "--json"}:
            if token == prefix[index]:
                index += 1
            continue
        if token.startswith("-"):
            continue
        if index >= len(prefix):
            return True
    return False


def _skip_global_token(words: list[str], index: int) -> int | None:
    """Advance past one root flag, or None if words[index] is not a global."""
    if index >= len(words):
        return None
    token = words[index]
    if token in GLOBAL_VALUE_FLAGS:
        return index + 2
    if token in GLOBAL_FLAGS or (token.startswith("-v") and set(token[1:]) <= {"v"}):
        return index + 1
    return None


def _collect_command_parts(words: list[str], start: int, rows: Mapping, prefix: list[str]) -> tuple[list[str], int]:
    parts = list(prefix)
    index = start
    while index < len(words):
        skipped = _skip_global_token(words, index)
        if skipped is not None:
            index = skipped
            continue
        token = words[index]
        if token.startswith("-"):
            break
        canon = _canonical(parts, token)
        candidate = " ".join([*parts, canon])
        if candidate in rows or any(
            name == candidate or name.startswith(candidate + " ") for name in rows
        ):
            parts.append(canon)
            index += 1
            continue
        break
    return parts, index


def validate_spa_command(command: str, *, require_aws_region: bool = False) -> str | None:
    """Return an error for a stale spa invocation, or None if it matches the schema."""
    try:
        words = shlex.split(command)
    except ValueError as exc:
        return "unparseable: %s (%s)" % (command, exc)
    if not words or not (words[0] == "spa" or str(words[0]).endswith("/spa")):
        return None
    rows = _by_name()
    parts, index = _collect_command_parts(words, 1, rows, [])
    if not parts and "--agent" in words:
        # spa --agent schema is agent schema; other --agent lines already matched.
        parts, index = _collect_command_parts(words, 1, rows, ["agent"])
    name = ""
    for length in range(len(parts), 0, -1):
        candidate = " ".join(parts[:length])
        if candidate in rows:
            name = candidate
            index = index - (len(parts) - length)
            break
    if not name:
        cursor = 1
        leftover = False
        while cursor < len(words):
            skipped = _skip_global_token(words, cursor)
            if skipped is not None:
                cursor = skipped
                continue
            leftover = True
            break
        if not leftover:
            return None
        rest = " ".join(words[1:])
        return "unknown command %s" % rest
    rest = words[index:]
    extra: list[str] = []
    skip_flags = False
    known = _schema_flags(name)
    i = 0
    while i < len(rest):
        token = rest[i]
        if skip_flags:
            i += 1
            continue
        if token == "--":
            skip_flags = True
            i += 1
            continue
        if token.startswith("-"):
            key = token.split("=", 1)[0]
            spec = known.get(key)
            if spec is None:
                return "unknown flag %s on `%s` (%s)" % (key, name, command)
            if "=" not in token and _takes_value(spec):
                i += 2
                continue
            i += 1
            continue
        extra.append(token)
        i += 1
    children = set(_next_words(name))
    entry = _entry(name)
    if extra and children and not _example_accepts_name(entry, name):
        first = extra[0]
        if COMMAND_WORD.match(first) and not _is_placeholder(first) and first not in children:
            return "unknown subcommand `%s %s`" % (name, first)
    if require_aws_region and name in AWS_DISCOVERY and "--region" not in rest:
        return "missing --region on `%s` (%s)" % (name, command)
    return None


def lint_spa_commands(text: str, source: Path | None = None) -> list[str]:
    """Lint extracted spa lines against COMMAND_SCHEMA (aliases resolved)."""
    require_region = False
    if source is not None:
        try:
            require_region = "skills" in source.resolve().relative_to(PROJECT_ROOT).parts
        except ValueError:
            require_region = "skills" in Path(source).parts
    errors = []
    label = str(source) if source is not None else "<text>"
    try:
        rel = Path(label)
        if rel.is_absolute():
            rel = rel.relative_to(PROJECT_ROOT)
        label = str(rel)
    except Exception:
        pass
    for line_no, command in extract_spa_commands(text):
        err = validate_spa_command(command, require_aws_region=require_region)
        if err:
            errors.append("%s:%d: %s" % (label, line_no, err))
    return errors


def lint_operator_docs_and_skills(paths: Iterable[Path] | None = None) -> list[str]:
    errors: list[str] = []
    for path in paths if paths is not None else operator_doc_paths():
        errors.extend(lint_spa_commands(path.read_text(encoding="utf-8"), source=path))
    return errors


def scan_secrets(text: str, source: Path | None = None, *, agent_facing: bool = False) -> list[str]:
    """PEM markers, secret-looking tokens, and -v on deploy/run in agent-facing files."""
    errors: list[str] = []
    label = str(source) if source is not None else "<text>"
    try:
        rel = Path(label)
        if rel.is_absolute():
            rel = rel.relative_to(PROJECT_ROOT)
        label = str(rel)
    except Exception:
        pass
    for line_no, line in enumerate(text.splitlines(), 1):
        if SECRET_TOKEN.search(line):
            errors.append("%s:%d: PEM or secret-looking token" % (label, line_no))
            continue
        if CREDENTIAL_KEY.search(line) and re.search(r":\s+\S", line) and not LOOKUP_ENV.search(line):
            if re.search(r":\s+['\"]?(?:true|false|yes|no|null|~)?['\"]?\s*$", line, re.IGNORECASE):
                continue
            if re.search(r":\s+\{", line):
                continue
            if re.search(r"^\s*\S*(password|secret|token|private[_-]?key)\S*\s*:", line, re.IGNORECASE):
                value = line.split(":", 1)[1].strip().strip("'\"")
                if value and value not in {"|", ">", ">-", "|-"} and not value.startswith("{{"):
                    if not re.match(r"^\$[A-Z_]+$", value) and "set / not set" not in line.lower():
                        errors.append("%s:%d: secret-looking name with a literal value" % (label, line_no))
                        continue
    if agent_facing:
        for line_no, command in extract_spa_commands(text):
            err = _verbose_on_deploy_run(command)
            if err:
                errors.append("%s:%d: %s" % (label, line_no, err))
    return errors


def _verbose_on_deploy_run(command: str) -> str | None:
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if not words or not (words[0] == "spa" or str(words[0]).endswith("/spa")):
        return None
    parts: list[str] = []
    for token in words[1:]:
        if token in GLOBAL_VALUE_FLAGS or token in GLOBAL_FLAGS:
            continue
        if token.startswith("-"):
            continue
        parts.append(_canonical(parts, token))
        if " ".join(parts) in {"deploy", "run"}:
            break
    name = ""
    for length in range(len(parts), 0, -1):
        candidate = " ".join(parts[:length])
        if candidate in {"deploy", "run"}:
            name = candidate
            break
    if name not in {"deploy", "run"}:
        return None
    if "--" in words:
        after = words[words.index("--") + 1 :]
        if any(VERBOSE_FLAG.match(token) for token in after):
            return "-v after -- on spa %s" % name
    if any(VERBOSE_FLAG.match(token) for token in words):
        return "-v on spa %s" % name
    return None


def scan_docs_and_skills(paths: Iterable[Path] | None = None) -> list[str]:
    errors: list[str] = []
    for path in paths if paths is not None else docs_and_skill_paths():
        try:
            rel_parts = path.resolve().relative_to(PROJECT_ROOT).parts
        except ValueError:
            rel_parts = path.parts
        agent_facing = rel_parts[0] in {"skills", ".agent"}
        errors.extend(
            scan_secrets(
                path.read_text(encoding="utf-8"),
                source=path,
                agent_facing=agent_facing,
            )
        )
    return errors


def _job_runs_pytest(run: str) -> bool:
    return any(
        token in run
        for token in (
            "run_cli_tests.sh",
            "run_ansible_tests.sh",
            "run_unit_tests.sh",
            "run_local_tests.sh",
            "pytest ",
        )
    )


def _markexpr_from_run(run: str, marker: str | None = None) -> str | None:
    match = SPA_CLI_MARKEXPR.search(run)
    if match:
        return match.group(1)
    match = SPA_ANSIBLE_MARKEXPR.search(run)
    if match:
        return match.group(1)
    match = PYTEST_M.search(run)
    if match:
        return match.group(1)
    for name, expr in RUNNER_MARKEXPR.items():
        if name in run:
            return expr
    if marker:
        return marker
    return None


def _expand_job_name(job: Mapping, row: Mapping | None = None) -> str:
    name = str(job.get("name") or "")
    if row is not None and "${{ matrix.name }}" in name:
        return str(row.get("name") or name)
    if name:
        return name
    return str(row.get("name") or "") if row else ""


def parse_ci_jobs(ci_text: str) -> list[dict]:
    """Every workflow job, including non-matrix pytest jobs (for example Ansible 3.15)."""
    data = yaml.safe_load(ci_text) or {}
    jobs = []
    for job_id, job in (data.get("jobs") or {}).items():
        if not isinstance(job, Mapping):
            continue
        matrix = ((job.get("strategy") or {}) or {}).get("matrix") or {}
        includes = list(matrix.get("include") or [])
        steps = list(job.get("steps") or [])
        if includes:
            for row in includes:
                run = str(row.get("run") or "")
                if not run:
                    run = "\n".join(str(step.get("run") or "") for step in steps if isinstance(step, Mapping))
                jobs.append(
                    {
                        "id": job_id,
                        "name": _expand_job_name(job, row),
                        "run": run,
                        "marker": row.get("marker"),
                        "steps": steps,
                        "row": row,
                    }
                )
            continue
        run = "\n".join(str(step.get("run") or "") for step in steps if isinstance(step, Mapping))
        jobs.append(
            {
                "id": job_id,
                "name": _expand_job_name(job) or str(job_id),
                "run": run,
                "marker": None,
                "steps": steps,
                "row": None,
            }
        )
    return jobs


def ci_job_names(ci_text: str) -> set[str]:
    return {job["name"] for job in parse_ci_jobs(ci_text) if job["name"]}


def ci_pytest_markexprs(ci_text: str) -> set[str]:
    exprs = set()
    for job in parse_ci_jobs(ci_text):
        if not _job_runs_pytest(job["run"]):
            continue
        expr = _markexpr_from_run(job["run"], job.get("marker"))
        if expr:
            exprs.add(expr)
    return exprs


def python_setup_steps(job: Mapping) -> list[dict]:
    found = []
    for step in job.get("steps") or []:
        if not isinstance(step, Mapping):
            continue
        uses = str(step.get("uses") or "")
        if "setup-python" not in uses:
            continue
        version = str((step.get("with") or {}).get("python-version") or "").strip().strip('"')
        found.append(
            {
                "version": version,
                "continue_on_error": bool(step.get("continue-on-error")),
            }
        )
    return found


def release_required_check_names(release_text: str) -> set[str]:
    match = REQUIRED_CHECKS_SENTENCE.search(release_text)
    if match is None:
        return set()
    return {name.strip() for name in BACKTICK_NAME.findall(match.group(1)) if name.strip()}
