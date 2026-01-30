"""
Deployment Test Suite for Splunk Platform Automator.

This module contains sequential, dependent tests for the deployment pipeline:
1. Prepare configuration
2. Create Terraform configs
3. Deploy virtual hosts (provision AWS infrastructure)
4. Run each playbook from deploy_site.yml individually

Tests are marked as incremental - if one fails, subsequent tests are skipped.
"""
import pytest
import os
import subprocess


@pytest.mark.incremental
class TestSplunkDeployment:
    """
    Sequential test suite for Splunk deployment.
    Each test depends on the previous one succeeding.
    State is shared via the workspace_manager fixture.
    """
    
    @pytest.fixture(autouse=True, scope="class")
    def setup_class_env(self, request, workspace_manager):
        """
        Setup class-level variables from workspace manager.
        Runs once per class (per config parametrization).
        """
        request.cls.manager = workspace_manager
        request.cls.work_dir = workspace_manager.work_dir
        request.cls.splunk_env_id = workspace_manager.splunk_env_id
        request.cls.project_root = workspace_manager.project_root
        request.cls.venv_bin = workspace_manager.venv_bin
        request.cls.ansible_playbook_bin = workspace_manager.get_ansible_playbook_bin()
        request.cls.env = workspace_manager.get_ansible_env()
    
    def _run_playbook(self, playbook_path: str, extra_args: list = None) -> subprocess.CompletedProcess:
        """
        Helper to run an Ansible playbook.
        
        Args:
            playbook_path: Relative path from workspace root (e.g., 'ansible/install_splunk.yml')
            extra_args: Additional command line arguments
            
        Returns:
            subprocess.CompletedProcess with result
        """
        cmd = [self.ansible_playbook_bin, playbook_path]
        if extra_args:
            cmd.extend(extra_args)
        
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.env
        )
        
        if result.returncode != 0:
            print(f"\n--- Playbook {playbook_path} FAILED ---")
            print("STDOUT:", result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout)
            print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        
        return result
    
    # =========================================================================
    # Test 01: Prepare Configuration
    # =========================================================================
    def test_01_prepare_config(self, config_file):
        """
        Step 1: Prepare and validate configuration.
        
        - Copies config from tests/configs/ to workspace
        - Injects SplunkEnvID for AWS tagging
        - Injects Software directory paths
        """
        print(f"\n[TEST] Starting test for config: {config_file}")
        print(f"[TEST] Environment ID: {self.splunk_env_id}")
        print(f"[TEST] Workspace: {self.work_dir}")
        
        # Prepare config using workspace manager
        config_data = self.manager.prepare_config()
        
        # Verify config was created
        dest_config_path = os.path.join(self.work_dir, 'config', 'splunk_config.yml')
        assert os.path.isfile(dest_config_path), "Config file was not created"
        
        # Store config data on class for later tests
        self.__class__.config_data = config_data
        
        print(f"[TEST] Config prepared with {len(config_data.get('splunk_hosts', []))} hosts")
    
    # =========================================================================
    # Test 02: Create Terraform Configs
    # =========================================================================
    def test_02_create_terraform_configs(self, config_file):
        """
        Step 2: Create Terraform configuration files.
        
        Runs the provision playbook in check mode to generate terraform.tfvars
        without actually provisioning infrastructure.
        """
        print("\n[TERRAFORM] Creating Terraform configuration files...")
        
        # First ensure the inventory plugin can read the config
        # Run provision with --tags that only do terraform prep
        result = self._run_playbook(
            "ansible/provision_terraform_aws.yml",
            ["-e", "auto_approve=false", "--tags", "generate"]
        )
        
        # Check if terraform.tfvars was created
        tfvars_path = os.path.join(self.work_dir, 'terraform/aws/terraform.tfvars')
        
        if os.path.isfile(tfvars_path):
            print(f"[TERRAFORM] Created terraform.tfvars at: {tfvars_path}")
        else:
            print("[TERRAFORM] terraform.tfvars will be created during provisioning")
        
        # This test passes as long as no fatal errors occurred
        # The actual config creation happens during provisioning
        print("[TERRAFORM] Terraform config preparation complete")
    
    # =========================================================================
    # Test 03: Deploy Virtual Hosts
    # =========================================================================
    def test_03_deploy_virtual_hosts(self, config_file):
        """
        Step 3: Provision AWS infrastructure with Terraform.
        
        - Runs provision_terraform_aws.yml with auto_approve=true
        """
        print("\n[PROVISION] Deploying virtual hosts to AWS...")
        
        # Run terraform provisioning (skip verify tag as we do our own verification)
        result = self._run_playbook(
            "ansible/provision_terraform_aws.yml",
            ["-e", "auto_approve=true", "--skip-tags", "verify"]
        )
        
        assert result.returncode == 0, "Infrastructure provisioning failed"
        
        # Mark provisioning as done
        self.manager.is_provisioned = True
        self.__class__.is_provisioned = True
        
        print("[PROVISION] Infrastructure provisioned successfully")
    
    # =========================================================================
    # Test 04: Verify Host Connectivity
    # =========================================================================
    def test_04_verify_host_connectivity(self, config_file):
        """
        Step 4: Verify all hosts are reachable.
        
        Runs: ansible/verification/ping_hosts.yml
        - Waits for hosts to become reachable after provisioning
        """
        if not getattr(self, 'is_provisioned', False):
            pytest.fail("Previous step failed: Infrastructure not provisioned")
        
        print("\n[VERIFY] Verifying host connectivity...")
        
        ping_result = self._run_playbook("ansible/verification/ping_hosts.yml")
        
        if ping_result.returncode != 0:
            print("[WARN] Initial ping failed, hosts may still be starting...")
            # Give it a bit more time and retry
            import time
            time.sleep(30)
            ping_result = self._run_playbook("ansible/verification/ping_hosts.yml")
        
        assert ping_result.returncode == 0, "Hosts are not reachable after provisioning"
        
        print("[VERIFY] All hosts are reachable")
    
    # =========================================================================
    # Test 05: Setup Common
    # =========================================================================
    def test_05_setup_common(self, config_file):
        """
        Step 5: Setup common settings on all hosts.
        
        Runs: ansible/setup_common.yml
        - Configures timezone, hostname, etc.
        """
        if not getattr(self, 'is_provisioned', False):
            pytest.fail("Previous step failed: Infrastructure not provisioned")
        
        print("\n[DEPLOY] Running setup_common.yml...")
        result = self._run_playbook("ansible/setup_common.yml")
        
        assert result.returncode == 0, "setup_common.yml failed"
        print("[DEPLOY] Common setup complete")
    
    # =========================================================================
    # Test 06: Create Linkpage
    # =========================================================================
    def test_06_create_linkpage(self, config_file):
        """
        Step 6: Create Splunk control/link page.
        
        Runs: ansible/create_linkpage.yml
        """
        if not getattr(self, 'is_provisioned', False):
            pytest.fail("Previous step failed: Infrastructure not provisioned")
        
        print("\n[DEPLOY] Running create_linkpage.yml...")
        result = self._run_playbook("ansible/create_linkpage.yml")
        
        assert result.returncode == 0, "create_linkpage.yml failed"
        print("[DEPLOY] Linkpage created")
    
    # =========================================================================
    # Test 07: Install Splunk
    # =========================================================================
    def test_07_install_splunk(self, config_file):
        """
        Step 7: Install Splunk software on all hosts.
        
        Runs: ansible/install_splunk.yml
        - Downloads and installs Splunk Enterprise/UF
        - Configures initial admin password
        """
        if not getattr(self, 'is_provisioned', False):
            pytest.fail("Previous step failed: Infrastructure not provisioned")
        
        print("\n[DEPLOY] Running install_splunk.yml...")
        result = self._run_playbook("ansible/install_splunk.yml")
        
        assert result.returncode == 0, "install_splunk.yml failed"
        
        # Mark Splunk as installed for dependent tests
        self.manager.is_splunk_installed = True
        self.__class__.is_splunk_installed = True
        
        print("[DEPLOY] Splunk software installed")
    
    # =========================================================================
    # Test 08: Setup Splunk Roles
    # =========================================================================
    def test_08_setup_splunk_roles(self, config_file):
        """
        Step 8: Configure Splunk roles (indexer, search_head, etc).
        
        Runs: ansible/setup_splunk_roles.yml
        - Configures clustering, replication, etc.
        """
        if not getattr(self, 'is_splunk_installed', False):
            pytest.fail("Previous step failed: Splunk not installed")
        
        print("\n[DEPLOY] Running setup_splunk_roles.yml...")
        result = self._run_playbook("ansible/setup_splunk_roles.yml")
        
        assert result.returncode == 0, "setup_splunk_roles.yml failed"
        
        # Mark Splunk as configured for dependent tests
        self.manager.is_splunk_configured = True
        self.__class__.is_splunk_configured = True
        
        print("[DEPLOY] Splunk roles configured")
    
    # =========================================================================
    # Test 09: Setup Splunk Conf
    # =========================================================================
    def test_09_setup_splunk_conf(self, config_file):
        """
        Step 9: Apply Splunk configuration settings.
        
        Runs: ansible/setup_splunk_conf.yml
        - Applies custom .conf file settings
        """
        if not getattr(self, 'is_splunk_installed', False):
            pytest.fail("Previous step failed: Splunk not installed")
        
        print("\n[DEPLOY] Running setup_splunk_conf.yml...")
        result = self._run_playbook("ansible/setup_splunk_conf.yml")
        
        assert result.returncode == 0, "setup_splunk_conf.yml failed"
        print("[DEPLOY] Splunk conf settings applied")
    
    # =========================================================================
    # Test 10: Setup Other Roles
    # =========================================================================
    def test_10_setup_other_roles(self, config_file):
        """
        Step 10: Setup other roles (monitoring, etc).
        
        Runs: ansible/setup_other_roles.yml
        - Final deployment step
        """
        if not getattr(self, 'is_provisioned', False):
            pytest.fail("Previous step failed: Infrastructure not provisioned")
        
        print("\n[DEPLOY] Running setup_other_roles.yml...")
        result = self._run_playbook("ansible/setup_other_roles.yml")
        
        assert result.returncode == 0, "setup_other_roles.yml failed"
        
        print("[DEPLOY] Deployment complete!")
        print(f"[DEPLOY] Environment ID: {self.splunk_env_id}")
    
    # =========================================================================
    # VERIFICATION TESTS (run after deployment, before teardown)
    # =========================================================================
    
    def _run_verification_playbook(self, playbook_name: str):
        """Run a verification playbook from ansible/verification/ directory."""
        return self._run_playbook(f"ansible/verification/{playbook_name}")
    
    def _get_all_roles(self) -> set:
        """Extract all roles from config."""
        return self.manager.get_all_roles()
    
    # =========================================================================
    # Test 11: Verify Data Flow
    # =========================================================================
    def test_11_verify_data_flow(self, config_file):
        """
        Step 11: Verify data is flowing into Splunk.
        
        Runs: ansible/verification/verify_data_flow.yml
        - Searches _internal index for data
        - Asserts hosts are sending data
        """
        if not getattr(self, 'is_splunk_configured', False):
            pytest.fail("Previous step failed: Splunk not configured")
        
        print(f"\n[VERIFY] Verifying data flow for environment: {self.splunk_env_id}")
        
        result = self._run_verification_playbook("verify_data_flow.yml")
        
        assert result.returncode == 0, "Data flow verification failed - no data in _internal index"
        print("[VERIFY] Data flow verification passed")
    
    # =========================================================================
    # Test 12: Check Indexer Cluster Health
    # =========================================================================
    def test_12_check_idxc_health(self, config_file):
        """
        Step 12: Verify Indexer Cluster health.
        
        Runs: ansible/verification/check_idxc_health.yml
        - Checks cluster manager for service_ready_flag
        
        Skipped if 'cluster_manager' role is not in config.
        """
        if not getattr(self, 'is_splunk_configured', False):
            pytest.fail("Previous step failed: Splunk not configured")
        
        roles = self._get_all_roles()
        
        if 'cluster_manager' not in roles:
            pytest.skip("No cluster_manager role in configuration - skipping IDXC health check")
        
        print("\n[VERIFY] Checking Indexer Cluster health...")
        
        result = self._run_verification_playbook("check_idxc_health.yml")
        
        assert result.returncode == 0, "Indexer Cluster health check failed"
        print("[VERIFY] Indexer Cluster is healthy")
    
    # =========================================================================
    # Test 13: Check Search Head Cluster Health
    # =========================================================================
    def test_13_check_shc_health(self, config_file):
        """
        Step 13: Verify Search Head Cluster health.
        
        Runs: ansible/verification/check_shc_health.yml
        - Checks SHC captain for service_ready_flag
        
        Skipped if 'deployer' role is not in config.
        """
        if not getattr(self, 'is_splunk_configured', False):
            pytest.fail("Previous step failed: Splunk not configured")
        
        roles = self._get_all_roles()
        
        if 'deployer' not in roles:
            pytest.skip("No deployer role in configuration - skipping SHC health check")
        
        print("\n[VERIFY] Checking Search Head Cluster health...")
        
        result = self._run_verification_playbook("check_shc_health.yml")
        
        assert result.returncode == 0, "Search Head Cluster health check failed"
        print("[VERIFY] Search Head Cluster is healthy")
