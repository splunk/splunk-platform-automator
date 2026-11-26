"""
Standalone verification against a deployed env (including --local).

Live AWS coverage lives in test_deployment.py; this module keeps spa run
verification/<stem> for an already-deployed environment.
"""
import os

import pytest
import yaml

pytestmark = [pytest.mark.aws, pytest.mark.incremental]


class TestSplunkVerification:
    @pytest.fixture(autouse=True, scope="class")
    def setup_class_env(self, request, workspace_manager):
        request.cls.manager = workspace_manager
        request.cls.work_dir = workspace_manager.work_dir
        request.cls.env_dir = getattr(workspace_manager, "env_dir", None)
        request.cls.splunk_env_id = workspace_manager.splunk_env_id
        if workspace_manager.config_data is None:
            config_path = os.path.join(workspace_manager.work_dir, "config", "splunk_config.yml")
            env_dir = getattr(workspace_manager, "env_dir", None)
            if env_dir:
                config_path = os.path.join(env_dir, "config", "splunk_config.yml")
            if os.path.isfile(config_path):
                with open(config_path, encoding="utf-8") as handle:
                    workspace_manager.config_data = yaml.safe_load(handle)
        request.cls.config_data = workspace_manager.config_data

    def _run_spa(self, args, extra=None):
        return self.manager.run_spa(args, extra=extra)

    def _get_all_roles(self) -> set:
        return self.manager.get_all_roles()

    def _check_deployment_complete(self):
        if getattr(self.manager, "is_splunk_configured", False):
            return
        config_path = os.path.join(self.work_dir, "config", "splunk_config.yml")
        env_dir = getattr(self.manager, "env_dir", None)
        if env_dir:
            config_path = os.path.join(env_dir, "config", "splunk_config.yml")
        if not os.path.isfile(config_path):
            pytest.fail("Deployment not complete: splunk_config.yml not found")

    def test_01_wait_for_splunk(self, topology_id):
        self._check_deployment_complete()
        print("\n[WAIT] spa run verification/wait_for_splunk")
        result = self._run_spa(["run", "verification/wait_for_splunk"])
        assert result.returncode == 0, "Timeout waiting for Splunk services to start"
        print("[WAIT] All Splunk services are running")

    @pytest.mark.always_run
    def test_02_wait_for_bucket_fixup(self, topology_id):
        self._check_deployment_complete()
        if "cluster_manager" not in self._get_all_roles():
            pytest.skip("No cluster_manager role in configuration - skipping bucket fixup wait")
        print("\n[WAIT] spa run verification/wait_for_bucket_fixup")
        result = self._run_spa(["run", "verification/wait_for_bucket_fixup"])
        assert result.returncode == 0, "Bucket fixup wait failed or timed out"
        print("[WAIT] Bucket fixup tasks complete")

    @pytest.mark.always_run
    def test_03_check_idxc_health(self, topology_id):
        self._check_deployment_complete()
        if "cluster_manager" not in self._get_all_roles():
            pytest.skip("No cluster_manager role in configuration - skipping IDXC health check")
        print("\n[VERIFY] spa run verification/check_idxc_health")
        result = self._run_spa(["run", "verification/check_idxc_health"])
        assert result.returncode == 0, "Indexer Cluster health check failed"
        print("[VERIFY] Indexer Cluster is healthy")

    @pytest.mark.always_run
    def test_04_wait_for_shc_captain(self, topology_id):
        self._check_deployment_complete()
        if "deployer" not in self._get_all_roles():
            pytest.skip("No deployer role in configuration - skipping SHC wait")
        print("\n[WAIT] spa run verification/wait_for_shc_captain")
        result = self._run_spa(["run", "verification/wait_for_shc_captain"])
        assert result.returncode == 0, "Wait for SHC Captain failed or timed out"
        print("[WAIT] Search Head Cluster is ready")

    @pytest.mark.always_run
    def test_05_check_shc_health(self, topology_id):
        self._check_deployment_complete()
        if "deployer" not in self._get_all_roles():
            pytest.skip("No deployer role in configuration - skipping SHC health check")
        print("\n[VERIFY] spa run verification/check_shc_health")
        result = self._run_spa(["run", "verification/check_shc_health"])
        assert result.returncode == 0, "Search Head Cluster health check failed"
        print("[VERIFY] Search Head Cluster is healthy")

    def test_06_verify_data_flow(self, topology_id):
        self._check_deployment_complete()
        print(f"\n[VERIFY] spa run verification/verify_data_flow ({self.splunk_env_id})")
        result = self._run_spa(["run", "verification/verify_data_flow"])
        assert result.returncode == 0, "Data flow verification failed - no data in _internal index"
        print("[VERIFY] Data flow verification passed")

    def test_07_verify_hec(self, topology_id):
        self._check_deployment_complete()
        print(f"\n[VERIFY] spa run verification/verify_hec ({self.splunk_env_id})")
        result = self._run_spa(["run", "verification/verify_hec", "--yes"])
        assert result.returncode == 0, "HEC ingest verification failed"
        print("[VERIFY] HEC ingest verification passed")

    def test_08_verify_es(self, topology_id):
        self._check_deployment_complete()
        apps = ((self.config_data or {}).get("splunk_app_deployment") or {}).get("apps") or []
        installed_es = [
            app
            for app in apps
            if isinstance(app, dict)
            and str(app.get("premium_app") or "").strip().lower() == "es"
            and str(app.get("state", "installed")).strip().lower() != "absent"
        ]
        if not installed_es:
            pytest.skip("No installed premium_app: es in configuration - skipping ES health check")
        print(f"\n[VERIFY] spa run verification/verify_es ({self.splunk_env_id})")
        result = self._run_spa(
            ["run", "verification/verify_es"],
            extra=["-e", "fail_on_mismatch=true"],
        )
        assert result.returncode == 0, "ES health verification failed"
        print("[VERIFY] ES health verification passed")
