# Splunk Platform Automator Testing Framework

This directory contains an automated testing framework for Splunk deployments using Terraform (AWS) and Ansible. The framework uses `pytest` to orchestrate the lifecycle of infrastructure provisioning, software deployment, and verification.

## Prerequisites

1.  **Python 3.10+**
2.  **AWS Credentials**: Export your AWS credentials as environment variables:
    ```bash
    export AWS_ACCESS_KEY_ID="your_access_key"
    export AWS_SECRET_ACCESS_KEY="your_secret_key"
    ```
3.  **SSH Key**: Ensure the SSH private key defined in your test configs (e.g., `~/.ssh/aws_key.pem`) exists and is accessible.

## Project Structure

*   **`configs/*.yml`**: Test configuration files. Each YAML file represents a distinct test case (e.g., `single_aws.yml`).
*   **`conftest.py`**: Pytest fixtures handling:
    *   **Workspace Isolation**: Creates a temporary directory for each test run.
    *   **Env Setup**: Creates a dedicated venv and installs Ansible for each test.
    *   **Teardown**: Destroys resources and cleans up the workspace after tests.
*   **`test_deployments.py`**: The main test runner that executes the deployment steps (Prepare -> Provision -> Deploy -> Verify).
*   **`run_tests.sh`**: Helper script to setup the local runner environment and execute tests.
*   **`../ansible/verification/`**: Ansible playbooks used for verification steps.

## Running Tests

We provide the `run_tests.sh` script which handles the setup of the local Python test runner environment.

### 1. Run All Tests
```bash
./tests/run_tests.sh tests/test_deployments.py
```

### 2. Run a Specific Test Case
To run only the test configuration `single_aws.yml`:
```bash
./tests/run_tests.sh tests/test_deployments.py -k "single_aws"
```

### 3. Run in Parallel
This framework supports parallel execution using `pytest-xdist`. Each worker gets a completely isolated workspace and unique environment ID.
```bash
# Run with 2 parallel workers
./tests/run_tests.sh -n 2 tests/test_deployments.py
```

### 4. Running Specific Steps (Development/Debugging)
The tests are sequential. You can use `-k` to target specific steps, but usually you must run them in order or all together.

**Steps:**
1. `prepare_config`: Generates `splunk_config.yml` from the test config.
2. `provision`: Runs Terraform via Ansible.
3. `deploy`: Installs Splunk.
4. `verify_data_flow`: Checks internal logs.
5. `check_idxc_health`: Checks Indexer Cluster health (if applicable).
6. `check_shc_health`: Checks Search Head Cluster health (if applicable).

Example: Run only up to provisioning:
```bash
./tests/run_tests.sh tests/test_deployments.py -k "prepare or provision"
```

## Adding New Tests

1.  Create a new YAML file in `tests/configs/` (e.g., `cluster_test.yml`).
2.  Use the standard `splunk_config.yml` format.
3.  The framework will automatically discover the file and create a parameterized test case for it.

**Supported Verification Roles:**
*   **`cluster_manager`**: triggers `check_idxc_health`
*   **`deployer`**: triggers `check_shc_health`
*   **`search_head`**: triggers `verify_data_flow`

## Troubleshooting

*   **Live Output**: Use `-s` to see stdout/stderr in real-time (note: this disables capture):
    ```bash
    ./tests/run_tests.sh tests/test_deployments.py -s
    ```
*   **Keep Workspace**: To debug failed tests, you can comment out the `shutil.rmtree` line in `tests/conftest.py` to preserve the temporary workspace and inspect logs or SSH into instances.
