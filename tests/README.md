# Splunk Platform Automator Testing Framework

Automated testing framework for Splunk deployments using Terraform (AWS) and Ansible.

## Overview

This framework provides:
- **Parallel, isolated test execution** - Each test config runs in its own cloned workspace with dedicated venv
- **Two-phase testing** - Deployment tests followed by verification tests
- **Incremental tests** - Tests are sequential within each phase; failures skip subsequent tests
- **Auto-discovery** - YAML configs in `configs/` are automatically picked up as test cases

## Prerequisites

1. **Python 3.10+**
2. **AWS Credentials**:
   ```bash
   export AWS_ACCESS_KEY_ID="your_access_key"
   export AWS_SECRET_ACCESS_KEY="your_secret_key"
   ```
3. **SSH Key**: Ensure the SSH key defined in configs exists (e.g., `~/.ssh/aws_key.pem`)
4. **Software Directory**: Place Splunk installers in `../Software/` relative to project root

## Directory Structure

```
tests/
├── configs/                    # Test case configurations
│   ├── single_node.yml        # Single node (indexer + search_head)
│   └── cluster.yml            # Full cluster (IDXC + SHC)
├── conftest.py                # Pytest fixtures (workspace isolation)
├── pytest.ini                 # Pytest configuration
├── requirements.txt           # Test dependencies
├── test_deployment.py         # Phase 1: Infrastructure + Splunk deployment
├── test_verification.py       # Phase 2: Health verification tests
├── run_deployment_tests.sh    # Helper script for deployment tests
└── run_verification_tests.sh  # Helper script for verification tests
```

## Test Phases

### Phase 1: Deployment (`test_deployment.py`)

Sequential tests that build the environment:

| Step | Test | Description |
|------|------|-------------|
| 1 | `test_01_prepare_config` | Prepare splunk_config.yml |
| 2 | `test_02_create_terraform_configs` | Generate Terraform files |
| 3 | `test_03_deploy_virtual_hosts` | Provision AWS infrastructure |
| 4 | `test_04_verify_host_connectivity` | `ping_hosts.yml` |
| 5 | `test_05_setup_common` | `setup_common.yml` |
| 6 | `test_06_create_linkpage` | `create_linkpage.yml` |
| 7 | `test_07_install_splunk` | `install_splunk.yml` |
| 8 | `test_08_setup_splunk_roles` | `setup_splunk_roles.yml` |
| 9 | `test_09_setup_splunk_conf` | `setup_splunk_conf.yml` |
| 10 | `test_10_setup_other_roles` | `setup_other_roles.yml` |
| 11 | `test_11_verify_data_flow` | Verify data in `_internal` index |
| 12 | `test_12_check_idxc_health` | Indexer cluster health (if applicable) |
| 13 | `test_13_check_shc_health` | SHC cluster health (if applicable) |

> **Note:** Verification tests (11-13) are now integrated into the deployment suite. They run after deployment is complete but before infrastructure is torn down.

### Legacy: Standalone Verification (`test_verification.py`)

For standalone verification against existing infrastructure:

| Test | Description | Condition |
|------|-------------|-----------|
| `test_01_verify_data_flow` | Check _internal index | Always |
| `test_02_check_idxc_health` | Indexer cluster health | `cluster_manager` role |
| `test_03_check_shc_health` | Search head cluster health | `deployer` role |

## Running Tests

### Run All Deployment Tests
```bash
./tests/run_deployment_tests.sh
```

### Run Specific Config Only
```bash
./tests/run_deployment_tests.sh -k "single_node"
```

### Run in Parallel (2 workers)
```bash
./tests/run_deployment_tests.sh -n 2
```

### Run Verification Against Local Deployment

Run verification tests against an existing deployment (no workspace creation, no teardown):

```bash
./tests/run_verification_tests.sh --local -s
```

This mode:
- Uses `config/splunk_config.yml` from the project root
- Does NOT create a temp workspace or venv
- Does NOT destroy infrastructure after tests
- Uses ansible-playbook from your system PATH

### Run Standalone Verification Tests
```bash
./tests/run_verification_tests.sh
```

### Show Output in Real-time
```bash
./tests/run_deployment_tests.sh -s
```

### Run with Verbose Output
```bash
./tests/run_deployment_tests.sh -v
```

### Run Specific Test Steps Only
Use `-k` with test names to run only specific steps:

```bash
# Run only test 1 (prepare config)
./tests/run_deployment_tests.sh -k "test_01"

# Run only tests 1 and 2 (prepare config + create terraform configs)
./tests/run_deployment_tests.sh -k "test_01 or test_02"

# Run tests 1-3 for a specific config
./tests/run_deployment_tests.sh -k "(test_01 or test_02 or test_03) and single_node"
```

### Combine Options
```bash
# Run tests 1-2 in parallel with verbose output
./tests/run_deployment_tests.sh -n 2 -v -k "test_01 or test_02"
```

## Adding New Test Configurations

1. Create a new YAML file in `tests/configs/` (e.g., `my_test.yml`)
2. Use the standard `splunk_config.yml` format
3. The framework auto-discovers and creates a test case for it

Example minimal config:
```yaml
---
plugin: splunk-platform-automator

terraform:
  aws:
    region: "eu-central-1"
    ami_id: "ami-03cbad7144aeda3eb"
    key_name: "aws_key"
    ssh_private_key_file: "~/.ssh/aws_key.pem"
    security_group_names: ["Splunk_Basic"]
    instance_type: "c5.4xlarge"
    root_volume_size: 50

splunk_defaults:
  splunk_download:
    splunk: true

splunk_hosts:
  - name: splunk1
    roles:
      - indexer
      - search_head
```

## Workspace Isolation

Each test config gets:
- **Cloned codebase** in a temp directory
- **Dedicated Python venv** with Ansible installed
- **Unique SplunkEnvID** for AWS resource tagging

Workspaces are automatically cleaned up after tests complete (including infrastructure destruction).

## Troubleshooting

### Keep Workspace for Debugging
Comment out the cleanup in `conftest.py` to preserve temp directories:
```python
# In WorkspaceManager.cleanup():
# shutil.rmtree(self.work_dir, ignore_errors=True)
```

### View Test Output
```bash
./tests/run_deployment_tests.sh -s --tb=long
```

### Check AWS Resources
Look for resources tagged with `SplunkEnvID: test-<timestamp>-<uuid>`
