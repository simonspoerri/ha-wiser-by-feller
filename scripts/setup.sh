#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

alias lint='./scripts/lint.sh'

# Create config dir if not present
if [[ ! -d "${PWD}/config" ]]; then
    mkdir -p "${PWD}/config"
    hass --config "${PWD}/config" --script ensure_config
fi

# Install dependencies
python3 -m pip install --requirement requirements.txt
python3 -m pip install --requirement devcontainer/requirements.txt
