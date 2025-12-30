#!/bin/bash

# Script to run tests locally
# Usage: ./run_tests.sh [pytest arguments]

set -e

echo "Setting up test environment..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing test dependencies..."
pip install --upgrade pip
pip install -r requirements-test.txt

# Install package in development mode
echo "Installing package in development mode..."
pip install -e .

# Run tests
echo "Running tests..."
if [ $# -eq 0 ]; then
    # Default test run with coverage
    pytest tests/python/ -v --cov=cime_config --cov=param_templates --cov-report=term-missing --cov-report=html
else
    # Run with provided arguments
    pytest "$@"
fi

echo "Tests completed!"
echo "HTML coverage report available in htmlcov/index.html"