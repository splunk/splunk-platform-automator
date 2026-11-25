"""
Live deployment tests driven by bin/spa.

test_01 composes the suite topology and runs spa validate.
test_02 runs spa deploy --yes.
Later tests run spa run verification/<stem>.
Teardown is spa destroy --yes on the workspace fixture.
"""
import os

import pytest

pytestmark = [pytest.mark.aws, pytest.mark.incremental]


class TestSplunkDeployment:
    @pytest.fixture(autouse=True, scope="class")
    def setup_class_env(self, request, workspace_manager):
        request.cls.manager = workspace_manager
        request.cls.work_dir = workspace_manager.work_dir
        request.cls.env_dir = workspace_manager.env_dir
        request.cls.splunk_env_id = workspace_manager.splunk_env_id
        request.cls.project_root = workspace_manager.project_root

    def _run_spa(self, args, extra=None):
        return self.manager.run_spa(args, extra=extra)

    def test_01_prepare_config(self, topology_id):
        print(f"\n[TEST] Starting topology: {topology_id}")
        print(f"[TEST] Environment ID: {self.splunk_env_id}")
        print(f"[TEST] Env dir: {self.env_dir}")

        config_data = self.manager.prepare_config()
        dest_config_path = os.path.join(self.env_dir, "config", "splunk_config.yml")
        assert os.path.isfile(dest_config_path), "Config file was not created"
        self.__class__.config_data = config_data

        result = self._run_spa(["validate"])
        assert result.returncode == 0, "spa validate failed"
        print(f"[TEST] Config prepared with {len(config_data.get('splunk_hosts', []))} host entries")

    def test_02_deploy(self, topology_id):
        print("\n[DEPLOY] spa deploy --yes")
        self.manager.is_provisioned = True
        result = self._run_spa(["deploy", "--yes"])
        assert result.returncode == 0, "spa deploy failed"
        self.manager.is_splunk_installed = True
        self.manager.is_splunk_configured = True
        self.manager.is_apps_deployed = True
        self.__class__.is_provisioned = True
        self.__class__.is_splunk_installed = True
        self.__class__.is_splunk_configured = True
        self.__class__.is_apps_deployed = True
        print("[DEPLOY] spa deploy complete")

    def _get_all_roles(self) -> set:
        return self.manager.get_all_roles()

    def test_03_wait_for_splunk(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        print("\n[WAIT] spa run verification/wait_for_splunk")
        result = self._run_spa(["run", "verification/wait_for_splunk"])
        assert result.returncode == 0, "Timeout waiting for Splunk services to start"
        print("[WAIT] All Splunk services are running")

    @pytest.mark.always_run
    def test_04_wait_for_bucket_fixup(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        if "cluster_manager" not in self._get_all_roles():
            pytest.skip("No cluster_manager role in configuration - skipping bucket fixup wait")
        print("\n[WAIT] spa run verification/wait_for_bucket_fixup")
        result = self._run_spa(["run", "verification/wait_for_bucket_fixup"])
        assert result.returncode == 0, "Bucket fixup wait failed or timed out"
        print("[WAIT] Bucket fixup tasks complete")

    @pytest.mark.always_run
    def test_05_check_idxc_health(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        if "cluster_manager" not in self._get_all_roles():
            pytest.skip("No cluster_manager role in configuration - skipping IDXC health check")
        print("\n[VERIFY] spa run verification/check_idxc_health")
        result = self._run_spa(["run", "verification/check_idxc_health"])
        assert result.returncode == 0, "Indexer Cluster health check failed"
        print("[VERIFY] Indexer Cluster is healthy")

    @pytest.mark.always_run
    def test_06_wait_for_shc_captain(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        if "deployer" not in self._get_all_roles():
            pytest.skip("No deployer role in configuration - skipping SHC wait")
        print("\n[WAIT] spa run verification/wait_for_shc_captain")
        result = self._run_spa(["run", "verification/wait_for_shc_captain"])
        assert result.returncode == 0, "Wait for SHC Captain failed or timed out"
        print("[WAIT] Search Head Cluster is ready")

    @pytest.mark.always_run
    def test_07_check_shc_health(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        if "deployer" not in self._get_all_roles():
            pytest.skip("No deployer role in configuration - skipping SHC health check")
        print("\n[VERIFY] spa run verification/check_shc_health")
        result = self._run_spa(["run", "verification/check_shc_health"])
        assert result.returncode == 0, "Search Head Cluster health check failed"
        print("[VERIFY] Search Head Cluster is healthy")

    def test_08_verify_data_flow(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        print(f"\n[VERIFY] spa run verification/verify_data_flow ({self.splunk_env_id})")
        result = self._run_spa(["run", "verification/verify_data_flow"])
        assert result.returncode == 0, "Data flow verification failed - no data in _internal index"
        print("[VERIFY] Data flow verification passed")

    def test_09_verify_hec(self, topology_id):
        if not getattr(self, "is_splunk_configured", False):
            pytest.fail("Previous step failed: Splunk not configured")
        print(f"\n[VERIFY] spa run verification/verify_hec ({self.splunk_env_id})")
        result = self._run_spa(["run", "verification/verify_hec", "--yes"])
        assert result.returncode == 0, "HEC ingest verification failed"
        print("[VERIFY] HEC ingest verification passed")

    def test_10_verify_app_deployment(self, topology_id):
        if not getattr(self, "is_apps_deployed", False):
            pytest.fail("Previous step failed: Apps not deployed")
        print(f"\n[VERIFY] spa run verification/verify_app_deployment ({self.splunk_env_id})")
        result = self._run_spa(
            ["run", "verification/verify_app_deployment"],
            extra=["-e", "fail_on_mismatch=true"],
        )
        assert result.returncode == 0, "App deployment verification failed - apps do not match configuration"
        print("[VERIFY] App deployment verification passed")
