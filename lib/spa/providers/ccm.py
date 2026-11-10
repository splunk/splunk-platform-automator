"""Corporate Cloud Manager (CCM) EC2 lifecycle. Slice 1 is detect and state only."""

from __future__ import annotations

from typing import Any, Dict, List

from spa.paths import SpaPaths
from spa.providers import ProviderError, ProvisionState


class Provider:
    name = "ccm"

    def __init__(self, paths: SpaPaths, config: Dict[str, Any]):
        self.paths = paths
        # Slice 3 reads these from the ccm: block (not hardcoded here):
        # operating_system, instance_type, disk_storage, key_name (API ssh_key_name),
        # ssh_private_key_file, ssh_username.
        self.config = config
        self.state_dir = paths.spa_env_dir / "ccm"

    def provision_state(self) -> ProvisionState:
        state_file = self.state_dir / "state.json"
        if not state_file.is_file():
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="No CCM state for this env: %s" % self.state_dir,
                hint="spa provision --yes",
            )
        return ProvisionState(provider=self.name, provisioned=True)

    def _not_implemented(self, action: str) -> None:
        raise ProviderError("CCM %s is not implemented yet." % action)

    def provision(self, extra: List[str], **kwargs: Any) -> int:
        del extra, kwargs
        self._not_implemented("provision")

    def destroy(self, extra: List[str], **kwargs: Any) -> int:
        del extra, kwargs
        self._not_implemented("destroy")

    def suspend(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self._not_implemented("suspend")

    def resume(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self._not_implemented("resume")
