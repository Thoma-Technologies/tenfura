#!/bin/bash

set -e

git pull

# Install rust and cargo
if [ ! -f "$HOME/.cargo/env" ]
then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi

# Update your shell's source to include Cargo's path
source "$HOME/.cargo/env"

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
            pip3 install -r requirements.txt
            cp requirements.txt .dependencies_installed
        fi
    else
        echo "Installing packages for the first time"
        pip3 install -r requirements.txt
        cp requirements.txt .dependencies_installed
    fi
fi

if ! command -v npm &> /dev/null
then
    curl -sL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

if ! command -v pm2 &> /dev/null
then
    sudo npm install pm2 -g
fi

echo "Command: '$1'"
echo "Args: '${@:2}'"
if [ "$1" = "validator" ]; then
    pm2 start validator.py -- "${@:2}"
elif [ "$1" = "miner" ]; then
    pm2 start miner.py -- "${@:2}"
fi
