#!/bin/bash
set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Set the virtual environment directory
VENV_DIR="$PROJECT_ROOT/tests/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install dependencies
echo "Installing/Updating dependencies..."
pip install --upgrade pip -q
pip install -r "$PROJECT_ROOT/tests/requirements.txt" -q

# Run tests
echo "Running tests..."
# Pass all arguments to pytest
pytest -c "$PROJECT_ROOT/tests/pytest.ini" "$@"
