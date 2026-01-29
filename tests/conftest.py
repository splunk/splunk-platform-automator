"""
Pytest fixtures for Splunk Platform Automator Testing Framework.

Provides workspace isolation with cloned codebase and dedicated venv per test config.
"""
import pytest
import os
import sys
import shutil
import tempfile
import uuid
import yaml
import subprocess
import time
import glob


def get_test_configs():
    """
    Discovers all YAML config files in tests/configs/
    Returns a list of filenames (not full paths) to be used as test IDs.
    """
    config_dir = os.path.join(os.path.dirname(__file__), 'configs')
    if not os.path.isdir(config_dir):
        return []
    files = glob.glob(os.path.join(config_dir, '*.yml'))
    return [os.path.basename(f) for f in files]


def pytest_generate_tests(metafunc):
    """
    Dynamically parametrize tests based on config files found in tests/configs/.
    This runs at collection time.
    """
    if "config_file" in metafunc.fixturenames:
        configs = get_test_configs()
        if not configs:
            configs = ["NO_CONFIGS_FOUND"]
        metafunc.parametrize("config_file", configs, scope="class")


class WorkspaceManager:
    """
    Manages isolated workspace for a test run.
    Each test config gets its own:
    - Cloned codebase in temp directory
    - Dedicated Python venv with Ansible installed
    - Unique SplunkEnvID for AWS tagging
    """
    
    def __init__(self, config_file: str, worker_id: str, project_root: str):
        self.config_file = config_file
        self.worker_id = worker_id
        self.project_root = project_root
        self.work_dir = None
        self.venv_bin = None
        self.splunk_env_id = None
        self.config_data = None
        self.is_provisioned = False
        self.is_deployed = False
        
    def setup(self) -> dict:
        """Create isolated workspace with cloned codebase and venv."""
        # Create temp directory
        config_name = os.path.splitext(self.config_file)[0]
        self.work_dir = tempfile.mkdtemp(prefix=f"spa_test_{self.worker_id}_{config_name}_")
        print(f"\n[SETUP] Creating isolated workspace at: {self.work_dir}")
        
        # Clone the project files
        self._clone_codebase()
        
        # Create venv and install dependencies
        self._setup_venv()
        
        # Generate unique SplunkEnvID
        timestamp = int(time.time())
        short_uuid = uuid.uuid4().hex[:6]
        self.splunk_env_id = f"test-{timestamp}-{short_uuid}"
        
        # Prepare config file (so tests can run in any order)
        self.prepare_config()
        
        return self.get_env_data()
    
    def _clone_codebase(self):
        """Copy project files to workspace, excluding unnecessary directories."""
        def ignore_patterns(path, names):
            ignore_list = ['.git', '.vagrant', 'tests', 'venv', '.venv', 
                          '.idea', '__pycache__', '.terraform', 'node_modules']
            ignored = [n for n in names if n in ignore_list or 
                      n.endswith('.tfstate') or n.endswith('.tfstate.backup')]
            
            # Ignore inventory in project root
            if path == self.project_root and 'inventory' in names:
                ignored.append('inventory')
            
            # Ignore terraform generated files
            if path.endswith('terraform/aws'):
                if 'terraform.tfvars' in names:
                    ignored.append('terraform.tfvars')
                    
            return ignored
        
        try:
            shutil.copytree(self.project_root, self.work_dir, 
                          dirs_exist_ok=True, ignore=ignore_patterns)
        except Exception as e:
            print(f"Error copying project files: {e}")
            self.cleanup()
            raise
    
    def _setup_venv(self):
        """Create Python venv and install dependencies."""
        venv_dir = os.path.join(self.work_dir, "venv")
        print(f"[SETUP] Creating venv at: {venv_dir}")
        
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        
        # Determine venv paths
        if os.name == "nt":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            self.venv_bin = os.path.join(venv_dir, "Scripts")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            self.venv_bin = os.path.join(venv_dir, "bin")
        
        # Upgrade pip
        print("[SETUP] Installing dependencies in venv...")
        subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], 
                      check=True, capture_output=True)
        
        # Build install command
        req_files = ["ansible"]
        
        project_req = os.path.join(self.work_dir, "requirements.txt")
        if os.path.isfile(project_req):
            req_files.extend(["-r", project_req])
        
        # Install dependencies
        install_cmd = [venv_python, "-m", "pip", "install"] + req_files
        result = subprocess.run(install_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("Dependency installation failed!")
            print(result.stderr)
            self.cleanup()
            raise RuntimeError("Failed to setup venv dependencies")
    
    def get_env_data(self) -> dict:
        """Return workspace environment data."""
        return {
            "work_dir": self.work_dir,
            "splunk_env_id": self.splunk_env_id,
            "project_root": self.project_root,
            "venv_bin": self.venv_bin,
            "config_file": self.config_file,
        }
    
    def prepare_config(self) -> dict:
        """Prepare splunk_config.yml with injected settings."""
        src_config_path = os.path.join(self.project_root, 'tests/configs', self.config_file)
        dest_config_path = os.path.join(self.work_dir, 'config', 'splunk_config.yml')
        
        # Ensure config dir exists
        os.makedirs(os.path.dirname(dest_config_path), exist_ok=True)
        
        with open(src_config_path, 'r') as f:
            self.config_data = yaml.safe_load(f)
        
        # Inject SplunkEnvID into terraform.aws tags
        if 'terraform' not in self.config_data:
            self.config_data['terraform'] = {}
        if 'aws' not in self.config_data['terraform']:
            self.config_data['terraform']['aws'] = {}
        if 'tags' not in self.config_data['terraform']['aws']:
            self.config_data['terraform']['aws']['tags'] = {}
        
        self.config_data['terraform']['aws']['tags']['SplunkEnvID'] = self.splunk_env_id
        
        # Inject Software Directory Path
        software_dir = os.path.abspath(os.path.join(self.project_root, "..", "Software"))
        if os.path.isdir(software_dir):
            print(f"[CONFIG] Found Software directory at: {software_dir}")
            if 'splunk_dirs' not in self.config_data:
                self.config_data['splunk_dirs'] = {}
            self.config_data['splunk_dirs']['splunk_software_dir'] = software_dir
            self.config_data['splunk_dirs']['splunk_baseconfig_dir'] = software_dir
        
        with open(dest_config_path, 'w') as f:
            yaml.dump(self.config_data, f)
        
        return self.config_data
    
    def get_all_roles(self) -> set:
        """Extract all roles from config."""
        all_roles = set()
        if self.config_data and 'splunk_hosts' in self.config_data:
            for host in self.config_data['splunk_hosts']:
                if 'roles' in host:
                    all_roles.update(host['roles'])
        return all_roles
    
    def get_ansible_env(self) -> dict:
        """Get environment variables for Ansible execution."""
        env = os.environ.copy()
        env['ANSIBLE_CONFIG'] = os.path.join(self.work_dir, 'ansible.cfg')
        # Use workspace-specific fact cache to avoid conflicts between parallel workers
        env['ANSIBLE_CACHE_PLUGIN_CONNECTION'] = os.path.join(self.work_dir, '.ansible_fact_cache')
        return env
    
    def get_ansible_playbook_bin(self) -> str:
        """Get path to ansible-playbook in venv."""
        return os.path.join(self.venv_bin, "ansible-playbook")
    
    def destroy_infrastructure(self):
        """Destroy AWS infrastructure."""
        if not self.is_provisioned:
            return
            
        print("\n[TEARDOWN] Destroying infrastructure...")
        destroy_cmd = [
            self.get_ansible_playbook_bin(),
            "ansible/destroy_terraform_aws.yml",
            "-e", "auto_approve=true"
        ]
        
        try:
            result = subprocess.run(
                destroy_cmd,
                cwd=self.work_dir,
                check=False,
                capture_output=True,
                text=True,
                env=self.get_ansible_env()
            )
            if result.returncode != 0:
                print(f"[TEARDOWN] Destroy failed (exit code {result.returncode})")
        except Exception as e:
            print(f"Error during infrastructure destroy: {e}")
    
    def cleanup(self):
        """Clean up workspace directory."""
        if self.work_dir and os.path.exists(self.work_dir):
            print(f"[TEARDOWN] Cleaning up workspace: {self.work_dir}")
            shutil.rmtree(self.work_dir, ignore_errors=True)


# Global workspace storage for class-scoped fixture
_workspaces = {}


@pytest.fixture(scope="class")
def workspace_manager(request, worker_id, config_file):
    """
    Creates an isolated deployment workspace for each test class (config).
    
    Lifecycle:
    1. Create temp directory
    2. Clone the codebase (excluding .git, .vagrant, etc.)
    3. Create dedicated venv with Ansible
    4. Generate unique SplunkEnvID
    5. Yield workspace manager
    6. Teardown: destroy infrastructure, cleanup temp directory
    
    Args:
        request: pytest request fixture
        worker_id: xdist worker ID
        config_file: parametrized config file name (from pytest_generate_tests)
    """
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Create workspace manager
    manager = WorkspaceManager(config_file, worker_id, project_root)
    manager.setup()
    
    # Store globally for verification tests
    _workspaces[config_file] = manager
    
    yield manager
    
    # Teardown
    manager.destroy_infrastructure()
    manager.cleanup()
    
    # Remove from global storage
    _workspaces.pop(config_file, None)


@pytest.fixture(scope="class")
def deployment_env(workspace_manager):
    """
    Legacy-compatible fixture that returns environment dict.
    """
    return workspace_manager.get_env_data()


def get_workspace_for_config(config_file: str) -> WorkspaceManager:
    """Get existing workspace manager for a config file."""
    return _workspaces.get(config_file)


# ============================================================================
# Incremental testing hooks
# See https://docs.pytest.org/en/latest/example/simple.html#incremental-testing-test-steps
# ============================================================================

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Mark subsequent tests as xfail if a previous incremental test failed."""
    outcome = yield
    rep = outcome.get_result()
    
    if "incremental" in item.keywords:
        if rep.when == "call" and rep.failed:
            item.parent._previousfailed = item


def pytest_runtest_setup(item):
    """Skip tests if previous incremental test failed."""
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail(f"Previous test failed: {previousfailed.name}")


# ============================================================================
# Parallel execution support
# ============================================================================

@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """
    Assign xdist_group markers based on config_file parameter.
    
    This ensures that all tests for the same config_file run on the same worker,
    while different config_files can run in parallel on different workers.
    
    Note: tryfirst=True ensures this runs BEFORE xdist's hook processes markers.
    """
    for item in items:
        # Get the config_file from the test's parametrization
        if hasattr(item, 'callspec') and 'config_file' in item.callspec.params:
            config_file = item.callspec.params['config_file']
            # Use config file name (without extension) as the group name
            group_name = os.path.splitext(config_file)[0]
            # Add xdist_group marker for parallel distribution
            # Note: pytest-xdist requires positional argument, not name=
            item.add_marker(pytest.mark.xdist_group(group_name))


@pytest.fixture(scope="session")
def worker_id(request):
    """
    Get xdist worker ID or 'master' for non-parallel runs.
    """
    if hasattr(request.config, 'workerinput'):
        return request.config.workerinput['workerid']
    return "master"

