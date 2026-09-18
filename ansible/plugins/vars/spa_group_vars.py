"""Load $SPA_HOME/ansible/group_vars without a symlink in the env inventory."""

from __future__ import annotations

DOCUMENTATION = r"""
    name: spa_group_vars
    short_description: Framework group_vars from SPA_HOME
    description:
      - Loads ansible/group_vars from the SPA framework tree.
      - Avoids creating $SPA_ENV_DIR/inventory/group_vars as a symlink into the repo.
      - Complements host_group_vars so custom env playbooks and ansible-inventory
        still see ansible.yml and dynamic.yml. spa_paths.yml stays with the
        inventory plugin (resolved SPA_HOME / SPA_ENV_DIR).
    options: {}
"""

import os

from ansible.errors import AnsibleParserError
from ansible.inventory.group import InventoryObjectType
from ansible.plugins.vars import BaseVarsPlugin
from ansible.utils.vars import combine_vars

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
# ansible/plugins/vars -> ansible/group_vars
_FRAMEWORK_GROUP_VARS = os.path.realpath(os.path.join(_PLUGIN_DIR, "..", "..", "group_vars"))
# Resolved by the inventory plugin; loading the jinja file here would replace them.
_SKIP_BASENAMES = frozenset({"spa_paths.yml"})


class VarsModule(BaseVarsPlugin):
    REQUIRES_ENABLED = False
    is_stateless = True

    def get_vars(self, loader, path, entities, cache=True):
        if not isinstance(entities, list):
            entities = [entities]
        data = {}
        opath = _FRAMEWORK_GROUP_VARS
        if not os.path.isdir(opath):
            return data
        for entity in entities:
            try:
                entity_type = entity.base_type
                entity_name = entity.name
            except AttributeError as exc:
                raise AnsibleParserError(
                    "spa_group_vars: expected Host or Group, got %s" % type(entity)
                ) from exc
            if entity_type is not InventoryObjectType.GROUP:
                continue
            found = loader.find_vars_files(opath, entity_name)
            for found_file in found:
                if os.path.basename(found_file) in _SKIP_BASENAMES:
                    continue
                new_data = loader.load_from_file(found_file)
                if new_data:
                    data = combine_vars(data, new_data)
        return data
