"""
Verification Test Suite for Splunk Platform Automator.

This module contains verification tests that run AFTER deployment is complete:
1. verify_data_flow.yml - Always runs
2. check_idxc_health.yml - Runs if cluster_manager role present
3. check_shc_health.yml - Runs if deployer role present

These tests are independent of each other but require deployment to be complete.
"""
import pytest
import os
import subprocess
import yaml


@pytest.mark.incremental
class TestSplunkVerification:
    """
    Verification test suite for deployed Splunk environments.
    
    These tests validate that the deployment was successful by running
    Ansible verification playbooks against the deployed infrastructure.
    """
    
    @pytest.fixture(autouse=True, scope="class")
    def setup_class_env(self, request, workspace_manager):
        """
        Setup class-level variables from workspace manager.
        """
        request.cls.manager = workspace_manager
        request.cls.work_dir = workspace_manager.work_dir
        request.cls.splunk_env_id = workspace_manager.splunk_env_id
        request.cls.venv_bin = workspace_manager.venv_bin
        request.cls.ansible_playbook_bin = workspace_manager.get_ansible_playbook_bin()
        request.cls.env = workspace_manager.get_ansible_env()
        
        # Load config data if not already loaded
        if workspace_manager.config_data is None:
            config_path = os.path.join(workspace_manager.work_dir, 'config', 'splunk_config.yml')
            if os.path.isfile(config_path):
                with open(config_path, 'r') as f:
                    workspace_manager.config_data = yaml.safe_load(f)
        
        request.cls.config_data = workspace_manager.config_data
    
    def _run_verification_playbook(self, playbook_name: str) -> subprocess.CompletedProcess:
        """
        Run a verification playbook.
        
        Args:
            playbook_name: Name of playbook in ansible/verification/ directory
            
        Returns:
            subprocess.CompletedProcess with result
        """
        playbook_path = f"ansible/verification/{playbook_name}"
        
        print(f"\n[VERIFY] Running {playbook_name}...")
        
        cmd = [self.ansible_playbook_bin, playbook_path]
        
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.env
        )
        
        print(f"--- {playbook_name} Output ---")
        print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        
        if result.returncode != 0:
            print(f"--- {playbook_name} Error ---")
            print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        
        return result
    
    def _get_all_roles(self) -> set:
        """Extract all roles from config."""
        all_roles = set()
        if self.config_data and 'splunk_hosts' in self.config_data:
            for host in self.config_data['splunk_hosts']:
                if 'roles' in host:
                    all_roles.update(host['roles'])
        return all_roles
    
    def _check_deployment_complete(self):
        """Verify that deployment was completed."""
        # Check if the workspace indicates Splunk is configured
        if not getattr(self.manager, 'is_splunk_configured', False):
            # Try to check if splunk is actually running by looking for indicators
            # This allows verification to run even if deployment tests were run separately
            config_path = os.path.join(self.work_dir, 'config', 'splunk_config.yml')
            if not os.path.isfile(config_path):
                pytest.fail("Deployment not complete: splunk_config.yml not found")
    
    # =========================================================================
    # Test 01: Verify Data Flow
    # =========================================================================
    def test_01_verify_data_flow(self, config_file):
        """
        Verify that data is flowing into Splunk.
        
        Runs: ansible/verification/verify_data_flow.yml
        - Searches _internal index for data
        - Asserts hosts are sending data
        
        Always runs for any deployment.
        """
        self._check_deployment_complete()
        
        print(f"\n[VERIFY] Verifying data flow for environment: {self.splunk_env_id}")
        
        result = self._run_verification_playbook("verify_data_flow.yml")
        
        assert result.returncode == 0, "Data flow verification failed - no data in _internal index"
        print("[VERIFY] Data flow verification passed")
    
    # =========================================================================
    # Test 02: Check Indexer Cluster Health
    # =========================================================================
    def test_02_check_idxc_health(self, config_file):
        """
        Verify Indexer Cluster health.
        
        Runs: ansible/verification/check_idxc_health.yml
        - Checks cluster manager for service_ready_flag
        
        Only runs if 'cluster_manager' role is present in config.
        """
        self._check_deployment_complete()
        
        roles = self._get_all_roles()
        
        if 'cluster_manager' not in roles:
            pytest.skip("No cluster_manager role in configuration - skipping IDXC health check")
        
        print(f"\n[VERIFY] Checking Indexer Cluster health...")
        
        result = self._run_verification_playbook("check_idxc_health.yml")
        
        assert result.returncode == 0, "Indexer Cluster health check failed"
        print("[VERIFY] Indexer Cluster is healthy")
    
    # =========================================================================
    # Test 03: Check Search Head Cluster Health
    # =========================================================================
    def test_03_check_shc_health(self, config_file):
        """
        Verify Search Head Cluster health.
        
        Runs: ansible/verification/check_shc_health.yml
        - Checks SHC captain for service_ready_flag
        
        Only runs if 'deployer' role is present in config.
        """
        self._check_deployment_complete()
        
        roles = self._get_all_roles()
        
        if 'deployer' not in roles:
            pytest.skip("No deployer role in configuration - skipping SHC health check")
        
        print(f"\n[VERIFY] Checking Search Head Cluster health...")
        
        result = self._run_verification_playbook("check_shc_health.yml")
        
        assert result.returncode == 0, "Search Head Cluster health check failed"
        print("[VERIFY] Search Head Cluster is healthy")
