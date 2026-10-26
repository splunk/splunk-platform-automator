"""Shared sentences for missing operands and unknown catalog values.

Human stderr, the agent error string, and positional help use these words.
"""

from __future__ import annotations


TOPOLOGY_HELP = (
    "A topology feature id or an example stem. "
    "List them: spa init list. "
    "Example: spa config topology topology.c1"
)
PROVIDER_HELP = (
    "aws, virtualbox, or external, or a provider feature id. "
    "List them: spa init list. "
    "Example: spa config provider aws"
)
INIT_PROVIDER_HELP = (
    "Provider example: aws, virtualbox, or external (default: aws, or providers.yml)"
)
SET_PATH_HELP = (
    "A config path. Find one: spa config search QUERY. "
    "Then read it: spa config explain PATH. "
    "Example: spa config set os.time_zone Europe/Berlin"
)
UNSET_PATH_HELP = (
    "A config path. Find one: spa config search QUERY. "
    "Then read it: spa config explain PATH. "
    "Example: spa config unset os.time_zone"
)
SELECTOR_HELP = (
    "A config path for a new list entry. Find one: spa config search QUERY. "
    "Then read it: spa config explain PATH. "
    "Example: spa config add 'splunk_hosts[name=lm]' '{\"roles\":[\"license_manager\"]}'"
)
APP_ID_HELP = (
    "A Splunkbase id or an app name in this config. "
    "Find one: spa apps search QUERY. "
    "Example: spa apps remove 833"
)


def _needs(command: str, operand: str, detail: str) -> str:
    return "spa %s needs %s.\n%s" % (command, operand, detail)


MISSING_OPERAND = {
    ("spa config set", "PATH"): _needs("config set", "PATH", SET_PATH_HELP),
    ("spa config add", "SELECTOR"): _needs("config add", "SELECTOR", SELECTOR_HELP),
    ("spa config unset", "PATH"): _needs("config unset", "PATH", UNSET_PATH_HELP),
    ("spa config topology", "TOPOLOGY"): _needs("config topology", "TOPOLOGY", TOPOLOGY_HELP),
    ("spa config provider", "PROVIDER"): _needs("config provider", "PROVIDER", PROVIDER_HELP),
    ("spa apps remove", "APP_ID_OR_NAME"): _needs("apps remove", "APP_ID_OR_NAME", APP_ID_HELP),
}


def unknown_topology(name: str) -> str:
    return "Unknown topology: %s\n%s" % (name, TOPOLOGY_HELP)


def unknown_provider(name: str) -> str:
    return "Unknown provider: %s\n%s" % (name, PROVIDER_HELP)
