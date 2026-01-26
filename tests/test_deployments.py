import pytest
import os
import yaml
import subprocess
import glob

def get_test_configs():
    """
    Discovers all YAML config files in tests/configs/
    Returns a list of filenames (not full paths) to be used as test IDs.
    """
    config_dir = os.path.join(os.getcwd(), 'tests/configs')
    if not os.path.isdir(config_dir):
        return []
    files = glob.glob(os.path.join(config_dir, '*.yml'))
    return [os.path.basename(f) for f in files]

@pytest.mark.incremental
@pytest.mark.parametrize("config_file", get_test_configs())
class TestSplunkDeployment:
    """
    Class-based test suite for Splunk Deployment.
    Each method represents a step in the deployment pipeline.
    State is shared via the `deployment_env` class-scoped fixture.
    """
    
    @pytest.fixture(autouse=True, scope="class")
    def setup_class_env(self, request, deployment_env):
        """
        Setup class-level variables from the env fixture.
        This runs once per class (per parametrization).
        """
        request.cls.work_dir = deployment_env['work_dir']
        request.cls.splunk_env_id = deployment_env['splunk_env_id']
        request.cls.project_root = deployment_env['project_root']
        request.cls.venv_bin = deployment_env['venv_bin']
        request.cls.ansible_playbook_bin = os.path.join(deployment_env['venv_bin'], "ansible-playbook")
        # config_file is already set on the class by @pytest.mark.parametrize 
        # but we need to ensure it is accessible as an instance attribute if not already.
        # However, parametrize sets it as an argument to the test method, OR as an attribute if indirect?
        
        # ACTUALLY: When parametrizing a class, the parameters are passed to the fixtures/methods.
        # If we remove it from here, we need to get it from somewhere.
        # But wait, parametrize on class sets the attribute on the class instance?
        # No, it effectively creates multiple classes.
        
        # The issue is 'config_file' is a parameter, effectively a function-scoped fixture.
        # We can't use it in a class-scoped fixture.
        
        # SOLUTION: We don't need config_file in this fixture. 
        # We can access it in test_01 via 'self.config_file' IF we set it.
        # BUT pytest parametrization on class passes args to __init__? No.
        
        # It's cleaner to just not use config_file in this setup fixture, 
        # and instead rely on the fact that for class parametrization, we might need a workaround 
        # or just access it in the test methods (where it is available as arg if requested).
        
        # Set ANSIBLE_CONFIG to point to the file in the test workspace root
        # This ensures role_paths in ansible.cfg are respected
        request.cls.env = os.environ.copy()
        request.cls.env['ANSIBLE_CONFIG'] = os.path.join(deployment_env['work_dir'], 'ansible.cfg')

    def test_01_prepare_config(self, config_file):
        """Step 1: Prepare and Validate Configuration"""
        print(f"\n[TEST] Starting test for config: {config_file}")
        print(f"[TEST] Environment ID: {self.splunk_env_id}")
        
        # Store for other methods if needed (though they don't seem to use it explicitly other than for context)
        self.config_file = config_file
        
        src_config_path = os.path.join(self.project_root, 'tests/configs', config_file)
        dest_config_path = os.path.join(self.work_dir, 'config', 'splunk_config.yml')
        
        # Ensure config dir exists
        os.makedirs(os.path.dirname(dest_config_path), exist_ok=True)
        
        with open(src_config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Inject SplunkEnvID into terraform.aws tags
        if 'terraform' not in config_data: config_data['terraform'] = {}
        if 'aws' not in config_data['terraform']: config_data['terraform']['aws'] = {}
        if 'tags' not in config_data['terraform']['aws']: config_data['terraform']['aws']['tags'] = {}
            
        config_data['terraform']['aws']['tags']['SplunkEnvID'] = self.splunk_env_id
        
        # Inject Software Directory Path
        software_dir = os.path.abspath(os.path.join(self.project_root, "..", "Software"))
        if os.path.isdir(software_dir):
            print(f"[CONFIG] Found Software directory at: {software_dir}")
            if 'splunk_dirs' not in config_data: config_data['splunk_dirs'] = {}
            config_data['splunk_dirs']['splunk_software_dir'] = software_dir
            config_data['splunk_dirs']['splunk_baseconfig_dir'] = software_dir
        else:
            print(f"[WARN] Software directory not found at: {software_dir}")
        
        with open(dest_config_path, 'w') as f:
            yaml.dump(config_data, f)
            
        assert os.path.isfile(dest_config_path), "Config file was not created"
        
        # Store config_data for later steps (helper to check roles)
        self.__class__.config_data = config_data

    def test_02_provision(self, config_file):
        """Step 2: Provision Infrastructure with Terraform"""
        # Ensure step 1 succeeded
        dest_config_path = os.path.join(self.work_dir, 'config', 'splunk_config.yml')
        if not os.path.isfile(dest_config_path):
            pytest.fail("Previous step failed: Config file not found. Cannot provision.")

        print("[DEPLOY] Provisioning infrastructure...")
        
        # DEBUG: Check if plugin exists
        plugin_dir = os.path.join(self.work_dir, 'ansible/plugins/inventory')
        print(f"[DEBUG] Listing {plugin_dir}:")
        if os.path.exists(plugin_dir):
            print(os.listdir(plugin_dir))
        else:
            print("[DEBUG] Plugin directory does not exist!")

        print(f"[DEBUG] ANSIBLE_CONFIG={self.env.get('ANSIBLE_CONFIG')}")
        
        # DEBUG: Check if ansible sees the plugin
        subprocess.run([self.ansible_playbook_bin.replace('ansible-playbook', 'ansible-doc'), '-t', 'inventory', '-l'], cwd=self.work_dir, env=self.env)
        
        provision_cmd = [
            self.ansible_playbook_bin,
            "ansible/provision_terraform_aws.yml",
            "-e", "auto_approve=true"
        ]
        
        result = subprocess.run(
            provision_cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.env
        )
        
        if result.returncode != 0:
            print("Provisioning STDOUT:", result.stdout)
            print("Provisioning STDERR:", result.stderr)
        
        assert result.returncode == 0, "Infrastructure provisioning failed"
        
        # Wait for connectivity (ping)
        print("[DEPLOY] Verifying connectivity...")
        wait_cmd = [
            self.ansible_playbook_bin,
            "ansible/verification/ping_hosts.yml"
        ]
        
        wait_result = subprocess.run(
            wait_cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.env
        )
        
        if wait_result.returncode != 0:
            print("Wait STDOUT:", wait_result.stdout)
            print("Wait STDERR:", wait_result.stderr)
            
        # We assert on wait success too
        assert wait_result.returncode == 0, "Waiting for hosts failed"
        
        # Mark provisioning as done
        self.__class__.is_provisioned = True

    def test_03_deploy(self, config_file):
        """Step 3: Deploy Splunk Software"""
        # Ensure provisioning succeeded
        if not getattr(self, 'is_provisioned', False):
            pytest.fail("Previous step failed: Infrastructure not provisioned. Cannot deploy Splunk.")

        print("[DEPLOY] Deploying Splunk software...")
        deploy_cmd = [
            self.ansible_playbook_bin,
            "ansible/deploy_site.yml"
        ]
        
        result = subprocess.run(
            deploy_cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.env
        )
        
        if result.returncode != 0:
            print("Deploy STDOUT:", result.stdout)
            print("Deploy STDERR:", result.stderr)
            
        assert result.returncode == 0, "Splunk deployment playbook failed"
        
        # Mark deployment as done
        self.__class__.is_deployed = True

    def test_04_verify_data_flow(self, config_file):
        """Step 4: Verify Data Flow (Splunk Log Ingestion)"""
        # Ensure deployment succeeded
        if not getattr(self, 'is_deployed', False):
            pytest.fail("Previous step failed: Splunk not deployed. Cannot verify.")

        # Always run if search_head role is present
        roles = self._get_all_roles()
        if 'search_head' not in roles:
            pytest.skip("No search_head role detected")
            
        self._run_verification_playbook("verification/verify_data_flow.yml")

    def test_05_check_idxc_health(self, config_file):
        """Step 5: Verify Indexer Cluster Health"""
        # Ensure deployment succeeded
        if not getattr(self, 'is_deployed', False):
            pytest.fail("Previous step failed: Splunk not deployed. Cannot verify.")

        roles = self._get_all_roles()
        if 'cluster_manager' not in roles:
            pytest.skip("No cluster_manager role detected")
            
        self._run_verification_playbook("verification/check_idxc_health.yml")

    def test_06_check_shc_health(self, config_file):
        """Step 6: Verify Search Head Cluster Health"""
        # Ensure deployment succeeded
        if not getattr(self, 'is_deployed', False):
            pytest.fail("Previous step failed: Splunk not deployed. Cannot verify.")

        roles = self._get_all_roles()
        if 'deployer' not in roles:
            pytest.skip("No deployer role detected")
            
        self._run_verification_playbook("verification/check_shc_health.yml")

    def _get_all_roles(self):
        """Helper to extract all roles from config"""
        all_roles = set()
        if 'splunk_hosts' in self.config_data:
            for host in self.config_data['splunk_hosts']:
                if 'roles' in host:
                    all_roles.update(host['roles'])
        return all_roles

    def _run_verification_playbook(self, playbook_rel_path):
        """Helper to run a verification playbook"""
        # playbook_rel_path is passed as "verification/xxx.yml"
        # We need to prepend ansible/ for running from work_dir
        
        playbook_name = os.path.basename(playbook_rel_path)
        # Playbooks are in ansible/verification/
        pb_path = f"ansible/verification/{playbook_name}"
        
        print(f"[VERIFY] Running {playbook_name}...")
        
        cmd = [
            self.ansible_playbook_bin,
            pb_path
        ]
        
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.env
        )
        
        print(f"--- {playbook_name} Output ---")
        print(result.stdout)
        if result.stderr:
            print(f"--- {playbook_name} Error ---")
            print(result.stderr)
            
        assert result.returncode == 0, f"Verification failed: {playbook_name}"
