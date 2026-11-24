"""
Pytest fixtures for Splunk Platform Automator Testing Framework.

Live AWS tests compose suite + topology into an isolated SPA_ENV_DIR and call bin/spa.
"""
import pytest
import os
import sys
import json
import shutil
import tempfile
import uuid
import yaml
import subprocess
import time
from pathlib import Path

from deployment_compose import compose_deployment_config, load_suite, suite_topology_ids
from spa_testutil import AGENT_ENV_VARS

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
os.environ["PYTHONPATH"] = _LIB + (
    os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""
)

_TESTS_DIR = Path(__file__).resolve().parent
_DEPLOYMENT_ROOT = _TESTS_DIR / "deployment"


def pytest_generate_tests(metafunc):
    """Parametrize live tests from --deployment-suite (not tests/configs/*.yml)."""
    if "topology_id" not in metafunc.fixturenames:
        return
    if metafunc.config.getoption("--local", default=False):
        metafunc.parametrize("topology_id", ["local"], scope="class")
        return
    suite_id = metafunc.config.getoption("--deployment-suite") or "aws"
    suite = load_suite(_DEPLOYMENT_ROOT, suite_id)
    ids = suite_topology_ids(suite)
    if not ids:
        ids = ["NO_TOPOLOGIES_FOUND"]
    metafunc.parametrize("topology_id", ids, scope="class")


def _sibling_dir(project_root: str, *names: str):
    parent = Path(project_root).resolve().parent
    for name in names:
        candidate = parent / name
        if candidate.is_dir():
            return str(candidate)
    return None


class WorkspaceManager:
    """Isolated SPA_ENV_DIR per topology. SPA_HOME is this checkout; tests call bin/spa."""

    def __init__(self, topology_id: str, worker_id: str, project_root: str, suite_id: str = "aws"):
        self.topology_id = topology_id
        self.suite_id = suite_id
        self.worker_id = worker_id
        self.project_root = project_root
        self._workspace_root = None
        self.work_dir = project_root
        self.env_dir = None
        self.venv_bin = None
        self.splunk_env_id = None
        self.config_data = None
        self.is_provisioned = False
        self.is_splunk_installed = False
        self.is_splunk_configured = False
        self.is_apps_deployed = False
        self._keep_workspace = False

    def setup(self) -> dict:
        self._workspace_root = tempfile.mkdtemp(
            prefix=f"spa_test_{self.worker_id}_{self.topology_id}_"
        )
        self.env_dir = os.path.join(self._workspace_root, "env")
        os.makedirs(os.path.join(self.env_dir, "config"))
        os.makedirs(os.path.join(self.env_dir, "inventory"))
        os.makedirs(os.path.join(self.env_dir, "terraform", "aws"))
        software_dir = _sibling_dir(self.project_root, "Software")
        baseconfig_dir = _sibling_dir(self.project_root, "Baseconfigs", "baseconfigs")
        spa_yml = {"spa_home": self.project_root}
        if software_dir:
            spa_yml["software_dir"] = software_dir
        if baseconfig_dir:
            spa_yml["baseconfig_dir"] = baseconfig_dir
        with open(os.path.join(self.env_dir, ".spa.yml"), "w", encoding="utf-8") as handle:
            yaml.safe_dump(spa_yml, handle, sort_keys=False)
        print(f"\n[SETUP] Creating isolated env at: {self.env_dir}")

        timestamp = int(time.time())
        short_uuid = uuid.uuid4().hex[:6]
        self.splunk_env_id = f"test-{timestamp}-{short_uuid}"
        self.prepare_config()
        return self.get_env_data()

    def get_env_data(self) -> dict:
        return {
            "work_dir": self.work_dir,
            "env_dir": self.env_dir,
            "splunk_env_id": self.splunk_env_id,
            "project_root": self.project_root,
            "venv_bin": self.venv_bin,
            "topology_id": self.topology_id,
            "suite_id": self.suite_id,
        }

    def prepare_config(self, ami_resolver=None) -> dict:
        dest_config_path = os.path.join(self.env_dir, "config", "splunk_config.yml")
        os.makedirs(os.path.dirname(dest_config_path), exist_ok=True)
        self.config_data = compose_deployment_config(
            Path(self.project_root) / "tests",
            suite_id=self.suite_id,
            topology_id=self.topology_id,
            ami_resolver=ami_resolver,
        )
        aws = self.config_data.setdefault("terraform", {}).setdefault("aws", {})
        tags = aws.setdefault("tags", {})
        tags["SplunkEnvID"] = self.splunk_env_id
        tags["TestConfig"] = self.topology_id

        software_dir = _sibling_dir(self.project_root, "Software")
        baseconfig_dir = _sibling_dir(self.project_root, "Baseconfigs", "baseconfigs")
        if software_dir or baseconfig_dir:
            dirs = self.config_data.setdefault("splunk_dirs", {})
            if software_dir:
                dirs["splunk_software_dir"] = software_dir
            if baseconfig_dir:
                dirs["splunk_baseconfig_dir"] = baseconfig_dir

        with open(dest_config_path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self.config_data, handle, sort_keys=False)
        return self.config_data
    
    def get_all_roles(self) -> set:
        """Extract all roles from config, including iter host entries."""
        all_roles = set()
        if self.config_data and "splunk_hosts" in self.config_data:
            for host in self.config_data["splunk_hosts"]:
                if "roles" in host:
                    all_roles.update(host["roles"])
        return all_roles

    def spa_bin(self) -> str:
        return os.path.join(self.project_root, "bin", "spa")

    def get_spa_env(self) -> dict:
        env = os.environ.copy()
        for name in AGENT_ENV_VARS:
            env.pop(name, None)
        env["SPA_HOME"] = self.work_dir
        env["SPA_ENV_DIR"] = self.env_dir
        env["SPLUNK_CONFIG_FILE"] = os.path.join(self.env_dir, "config", "splunk_config.yml")
        env["ANSIBLE_CONFIG"] = os.path.join(self.work_dir, "ansible.cfg")
        admin = env.get("SPLUNK_ADMIN_PASSWORD")
        if admin:
            env.setdefault("SPLUNK_IDXC_PASSWORD", admin)
            env.setdefault("SPLUNK_SHC_PASSWORD", admin)
        return env

    def run_spa(self, args: list, extra: list = None) -> subprocess.CompletedProcess:
        cmd = [self.spa_bin(), *args]
        if extra:
            cmd.extend(["--", *extra])
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.get_spa_env(),
        )
        if result.returncode != 0:
            logs = os.path.join(self.env_dir, "logs")
            print(f"\n--- spa {' '.join(args)} FAILED (exit {result.returncode}) ---")
            print(f"Run log directory: {logs}")
            if result.stdout:
                print(result.stdout[-4000:])
            if result.stderr:
                print(result.stderr[-2000:])
            self._print_failed_runlog()
            self._archive_failed_run(args, result)
        return result

    def _archive_failed_run(self, args: list, result: subprocess.CompletedProcess) -> None:
        dest = (
            Path(self.project_root)
            / "tests"
            / ".deployment_failures"
            / f"{self.topology_id}_{self.splunk_env_id}_{args[0]}"
        )
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "stdout.txt").write_text(result.stdout or "", encoding="utf-8")
        (dest / "stderr.txt").write_text(result.stderr or "", encoding="utf-8")
        logs = Path(self.env_dir) / "logs" if self.env_dir else None
        if logs and logs.is_dir():
            shutil.copytree(logs, dest / "logs", dirs_exist_ok=True)
        print(f"[TEST] Archived failure output: {dest}")

    def _print_failed_runlog(self) -> None:
        logs = Path(self.env_dir) / "logs" if self.env_dir else None
        if not logs or not logs.is_dir():
            return
        printed = 0
        for path in sorted(logs.glob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = event.get("status")
                kind = event.get("kind")
                if status not in ("failed", "unreachable"):
                    continue
                if kind not in ("host_result", "phase_end"):
                    continue
                task = event.get("task") or event.get("phase_title") or kind
                host = event.get("host") or ""
                msg = str(event.get("msg") or event.get("text") or "")[:800]
                print(f"[RUNLOG] {path.name} {status} {host} {task}: {msg}")
                printed += 1
                if printed >= 20:
                    return

    def destroy_infrastructure(self):
        if not self.is_provisioned:
            return
        print("\n[TEARDOWN] spa destroy --yes")
        try:
            result = self.run_spa(["destroy", "--yes"])
            if result.returncode != 0:
                print(f"[TEARDOWN] Destroy failed (exit code {result.returncode})")
                print(f"[TEARDOWN] Keeping env dir for terraform state: {self.env_dir}")
                self._keep_workspace = True
        except Exception as exc:
            print(f"Error during infrastructure destroy: {exc}")
            self._keep_workspace = True

    def cleanup(self):
        if self._keep_workspace:
            print(f"[TEARDOWN] Preserving workspace: {self._workspace_root}")
            return
        root = self._workspace_root
        if root and os.path.exists(root):
            print(f"[TEARDOWN] Cleaning up workspace: {root}")
            shutil.rmtree(root, ignore_errors=True)


class LocalWorkspaceManager:
    """Run verification against an existing env. Does not compose or destroy."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.work_dir = project_root
        self.env_dir = os.environ.get("SPA_ENV_DIR", project_root)
        self.topology_id = "local"
        self.suite_id = None
        self.splunk_env_id = "local"
        self.config_data = None
        self.is_provisioned = True
        self.is_splunk_installed = True
        self.is_splunk_configured = True
        self.is_apps_deployed = True
        self._workspace_root = None
        config_path = os.path.join(self.env_dir, "config", "splunk_config.yml")
        if not os.path.isfile(config_path):
            config_path = os.path.join(project_root, "config", "splunk_config.yml")
        if os.path.isfile(config_path):
            with open(config_path, encoding="utf-8") as handle:
                self.config_data = yaml.safe_load(handle)

    def prepare_config(self, ami_resolver=None) -> dict:
        return self.config_data or {}

    @property
    def venv_bin(self) -> str:
        return ""

    def spa_bin(self) -> str:
        return os.path.join(self.project_root, "bin", "spa")

    def get_spa_env(self) -> dict:
        env = os.environ.copy()
        for name in AGENT_ENV_VARS:
            env.pop(name, None)
        env["SPA_HOME"] = self.work_dir
        env["SPA_ENV_DIR"] = self.env_dir
        env["ANSIBLE_CONFIG"] = os.path.join(self.work_dir, "ansible.cfg")
        return env

    def run_spa(self, args: list, extra: list = None) -> subprocess.CompletedProcess:
        cmd = [self.spa_bin(), *args]
        if extra:
            cmd.extend(["--", *extra])
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=self.get_spa_env(),
        )
        if result.returncode != 0:
            logs = os.path.join(self.env_dir, "logs")
            print(f"\n--- spa {' '.join(args)} FAILED (exit {result.returncode}) ---")
            print(f"Run log directory: {logs}")
            if result.stdout:
                print(result.stdout[-4000:])
            if result.stderr:
                print(result.stderr[-2000:])
        return result

    def get_all_roles(self) -> set:
        all_roles = set()
        if self.config_data and "splunk_hosts" in self.config_data:
            for host in self.config_data["splunk_hosts"]:
                if "roles" in host:
                    all_roles.update(host["roles"])
        return all_roles

    def get_env_data(self) -> dict:
        return {
            "work_dir": self.work_dir,
            "env_dir": self.env_dir,
            "splunk_env_id": self.splunk_env_id,
            "is_local": True,
        }

    def destroy_infrastructure(self):
        print("[LOCAL] Skipping infrastructure destroy in local mode")

    def cleanup(self):
        pass


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--local",
        action="store_true",
        default=False,
        help="Run verification against existing local deployment (no workspace creation)",
    )
    parser.addoption(
        "--deployment-suite",
        action="store",
        default="aws",
        help="Live suite id under tests/deployment/suites/ (default: aws)",
    )


def _ensure_local_test_env() -> None:
    """Writable per-worker ansible tmp so xdist workers do not share files."""
    from pathlib import Path

    from spa_testutil import worker_local_dir

    tests_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    ansible_tmp = worker_local_dir(tests_dir / ".ansible_tmp")
    ansible_tmp.mkdir(parents=True, exist_ok=True)
    os.environ["ANSIBLE_LOCAL_TMP"] = str(ansible_tmp)
    os.environ["ANSIBLE_LOCAL_TEMP"] = str(ansible_tmp)


def pytest_configure(config):
    """Strip inherited path vars for local runs; always set worker-local ansible tmp."""
    from spa_testutil import INHERITED_PATH_VARS, selects_local_tests

    markexpr = (config.option.markexpr or "").strip()
    if markexpr and selects_local_tests(markexpr):
        for name in INHERITED_PATH_VARS:
            os.environ.pop(name, None)
    _ensure_local_test_env()


@pytest.fixture(autouse=True)
def _isolated_user_spa_config(request, tmp_path, monkeypatch):
    """Tests must never write the operator's ~/.config/spa (paths.yml, environments.yml)."""
    if request.node.get_closest_marker("aws"):
        return
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))


@pytest.fixture(autouse=True)
def _no_live_cloud(request, monkeypatch):
    """Only aws-marked (manual) tests may reach AWS or CCM and create hosts."""
    if request.node.get_closest_marker("aws"):
        return
    from spa_testutil import LIVE_CLOUD_ENV_VARS, NO_LIVE_CLOUD_ENV

    for name in LIVE_CLOUD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in NO_LIVE_CLOUD_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(autouse=True)
def _default_spa_env_dir(request, tmp_path, monkeypatch):
    """Operator spa commands need an env dir; skip AWS workspaces and marked tests."""
    if request.node.get_closest_marker("aws"):
        return
    import spa_testutil

    if request.node.get_closest_marker("no_spa_env"):
        monkeypatch.delenv("SPA_ENV_DIR", raising=False)
        monkeypatch.setattr(spa_testutil, "DEFAULT_SUBPROCESS_ENV", {})
        return
    from spa_testutil import PROJECT_ROOT, write_min_env

    dest = write_min_env(tmp_path / "spa-operator-env")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(dest))
    monkeypatch.delenv("SPLUNK_CONFIG_FILE", raising=False)
    monkeypatch.setattr(
        spa_testutil,
        "DEFAULT_SUBPROCESS_ENV",
        {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)},
    )


# Global workspace storage for class-scoped fixture
_workspaces = {}


@pytest.fixture(scope="class")
def workspace_manager(request, worker_id, topology_id):
    """Isolated SPA_ENV_DIR per topology, or the existing env in --local mode."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if request.config.getoption("--local"):
        print("\n[LOCAL] Running in local mode against existing deployment")
        manager = LocalWorkspaceManager(project_root)
        _workspaces[topology_id] = manager
        yield manager
        _workspaces.pop(topology_id, None)
        return

    suite_id = request.config.getoption("--deployment-suite") or "aws"
    manager = WorkspaceManager(topology_id, worker_id, project_root, suite_id=suite_id)
    manager.setup()
    _workspaces[topology_id] = manager
    yield manager
    manager.destroy_infrastructure()
    manager.cleanup()
    _workspaces.pop(topology_id, None)


@pytest.fixture(scope="class")
def deployment_env(workspace_manager):
    """
    Legacy-compatible fixture that returns environment dict.
    """
    return workspace_manager.get_env_data()


def get_workspace_for_config(topology_id: str) -> WorkspaceManager:
    """Get existing workspace manager for a topology id."""
    return _workspaces.get(topology_id)


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
        # Check for always_run marker
        if "always_run" in item.keywords:
            return

        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail(f"Previous test failed: {previousfailed.name}")


# ============================================================================
# Parallel execution support
# ============================================================================

@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """
    Assign xdist_group markers from parametrized fixtures.

    topology_id groups keep a live topology on one worker. scenario_scope_result
    keeps succeeds/assertions/snapshot for one app-scope scenario on one worker.
    Requires --dist=loadgroup (run_local_tests.sh and run_ansible_tests.sh add it with -n).

    Also rejects a local node that the CLI help, CLI runtime, Ansible chunks,
    and unit CI jobs would each select more than once, so no node runs in two jobs.

    Note: tryfirst=True ensures this runs BEFORE xdist's hook processes markers
    and before -m deselects anything.
    """
    from spa_testutil import local_job_partition_errors, xdist_group_name

    errors = local_job_partition_errors(
        (item.nodeid, {mark.name for mark in item.iter_markers()}) for item in items
    )
    if errors:
        raise pytest.UsageError("Local CI job overlap:\n  " + "\n  ".join(errors))

    for item in items:
        if not hasattr(item, "callspec"):
            continue
        group_name = xdist_group_name(item.callspec.params)
        if group_name is not None:
            # pytest-xdist requires a positional argument, not name=
            item.add_marker(pytest.mark.xdist_group(group_name))


@pytest.fixture(scope="module")
def agent_schema():
    """Cached `spa agent schema` JSON for CLI-runtime tests that only read the catalog."""
    from spa_testutil import run_spa_inprocess

    result = run_spa_inprocess(["agent", "schema"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def worker_id(request):
    """
    Get xdist worker ID or 'master' for non-parallel runs.
    """
    if hasattr(request.config, 'workerinput'):
        return request.config.workerinput['workerid']
    return "master"

