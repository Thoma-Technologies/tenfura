#!/bin/bash

# Create virtual environment if it doesn't exist
if [ ! -d ".env" ]; then
    python3 -m venv .env
fi

# Activate virtual environment
source ./.env/bin/activate

# Add current directory to Python path
export PYTHONPATH="${PYTHONPATH}:./"

# Check if pip requirements are up to date
if [ -z "$CACHED_VENV" ]; then
    if [ -f ".dependencies_installed" ]; then
        if ! cmp -s .dependencies_installed requirements.txt; then
            echo "Requirements have changed, updating packages"
            pip3 install -r requirements.txt --no-deps
            cp requirements.txt .dependencies_installed
        fi
    else
        echo "Installing packages for the first time"
        pip3 install -r requirements.txt --no-deps
        cp requirements.txt .dependencies_installed
    fi
fi
