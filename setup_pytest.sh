#!/bin/bash
# Quick setup script for pytest

echo "Setting up pytest..."

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "Activating virtual environment..."
source venv/bin/activate

# Install pytest
echo "Installing pytest..."
pip install pytest

echo ""
echo "✓ Setup complete!"
echo ""
echo "To run tests:"
echo "  source venv/bin/activate"
echo "  pytest xtp/tests/test_engine_paths.py -v"
echo ""

