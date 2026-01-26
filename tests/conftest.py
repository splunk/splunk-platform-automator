import pytest
import os
import sys
import shutil
import tempfile
import uuid
import yaml
import subprocess
import time

@pytest.fixture(scope="class")
def deployment_env(tmp_path_factory, worker_id):
    """
    Creates an isolated deployment environment for each test.
    1. Creates a temp directory.
    2. Copies the project files.
    3. Generates a unique SplunkEnvID.
    4. Yields the environment details.
    5. Teardown: Destroys the infrastructure and cleans up.
    """
    # 1. Create a temp directory
    # Using tmp_path_factory to ensure uniqueness across workers
    # base_temp = tmp_path_factory.getbasetemp()
    # work_dir = base_temp / f"run_{uuid.uuid4().hex[:8]}"
    # work_dir.mkdir()
    
    # Alternatively, use standard tempfile for complete isolation outside pytest cache
    work_dir_path = tempfile.mkdtemp(prefix=f"spa_test_{worker_id}_")
    
    print(f"\n[SETUP] Creating isolated workspace at: {work_dir_path}")

    # 2. Copy the project files
    # We copy everything except the 'tests' directory itself to avoid recursion if we were running from root
    # and potential heavy artifacts if they are not excluded. 
    # For simplicity, we assume we are running from the project root.
    project_root = os.getcwd()
    
    # Define what to ignore
    def ignore_patterns(path, names):
        # Global ignores
        ignore_list = ['.git', '.vagrant', 'tests', 'venv', '.idea', '__pycache__', '.terraform']
        
        ignored = [n for n in names if n in ignore_list or n.endswith('.tfstate') or n.endswith('.tfstate.backup')]
        
        # Only ignore 'inventory' if it is in the project root
        if path == project_root and 'inventory' in names:
            ignored.append('inventory')
        
        # Explicitly ignore locally generated artifacts if we are visiting their directories
        if path.endswith('terraform/aws'):
            if 'terraform.tfvars' in names: ignored.append('terraform.tfvars')
            
        return ignored

    try:
        # We manually copy top-level items to avoid copying the 'tests' dir into itself
        # if we initiated the copy from the root.
        # But copytree with ignore is easier.
        shutil.copytree(project_root, work_dir_path, dirs_exist_ok=True, ignore=ignore_patterns)
    except Exception as e:
        print(f"Error copying project files: {e}")
        shutil.rmtree(work_dir_path)
        pytest.fail("Failed to setup workspace")

    # 3. Create venv and install dependencies
    venv_dir = os.path.join(work_dir_path, "venv")
    print(f"[SETUP] Creating venv at: {venv_dir}")
    subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)

    # Determine paths for pip and ansible-playbook in the venv
    if os.name == "nt":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        venv_bin = os.path.join(venv_dir, "Scripts")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_bin = os.path.join(venv_dir, "bin")

    # Install dependencies
    print("[SETUP] Installing dependencies in venv...")
    pip_cmd = [venv_python, "-m", "pip", "install", "--upgrade", "pip"]
    subprocess.run(pip_cmd, check=True)
    
    # Install ansible (latest) and requirements
    # We install ansible explicitly as requested, then project requirements
    req_files = []
    if os.path.isfile(os.path.join(work_dir_path, "requirements.txt")):
        req_files.append("-r")
        req_files.append(os.path.join(work_dir_path, "requirements.txt"))
    
    if os.path.isfile(os.path.join(work_dir_path, "tests", "requirements.txt")):
        req_files.append("-r")
        req_files.append(os.path.join(work_dir_path, "tests", "requirements.txt"))
        
    install_cmd = [venv_python, "-m", "pip", "install", "ansible"] + req_files
    
    # Run install (capture output to avoid clutter unless error)
    result = subprocess.run(install_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Dependency installation failed!")
        print(result.stderr)
        shutil.rmtree(work_dir_path)
        pytest.fail("Failed to setup venv dependencies")

    # 4. Generate unique SplunkEnvID
    # Format: test-<timestamp>-<short_uuid>
    timestamp = int(time.time())
    short_uuid = uuid.uuid4().hex[:6]
    splunk_env_id = f"test-{timestamp}-{short_uuid}"
    
    env_data = {
        "work_dir": work_dir_path,
        "splunk_env_id": splunk_env_id,
        "project_root": project_root,
        "venv_bin": venv_bin  # Pass bin dir to use ansible-playbook from venv
    }

    yield env_data

    # 6. Teardown
    print("\n[TEARDOWN] Destroying infrastructure...")
    # Use ansible-playbook from venv for destroy as well
    destroy_cmd = [
        os.path.join(venv_bin, "ansible-playbook"), 
        "ansible/destroy_terraform_aws.yml"
    ]
    
    # We need to run destroy in the temp workspace
    try:
        # Check if we should skip destroy (e.g. for debugging failure)
        # For now, always destroy
        subprocess.run(
            destroy_cmd, 
            cwd=work_dir_path, 
            check=False, # Don't fail the test if destroy fails, just log it
            env=os.environ.copy()
        )
    except Exception as e:
        print(f"Error during teardown: {e}")
    
    print(f"[TEARDOWN] Cleaning up workspace: {work_dir_path}")
    shutil.rmtree(work_dir_path)

# Incremental testing hook
# See https://docs.pytest.org/en/latest/example/simple.html#incremental-testing-test-steps

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    
    if "incremental" in item.keywords:
        # Check if test failed (not skipped) during call phase
        if rep.when == "call" and rep.failed:
            item.parent._previousfailed = item

def pytest_runtest_setup(item):
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed ({})".format(previousfailed.name))
