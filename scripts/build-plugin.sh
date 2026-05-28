#!/usr/bin/env bash
# scripts/build-plugin.sh
# Rebuilds and reinstalls the OpenClaw plugin after src/ changes.
# Usage: ./scripts/build-plugin.sh [--skip-install]
set -euo pipefail

SKIP_INSTALL=${1:-""}

echo "Building TypeScript plugin..."
cd openclaw-plugin-testflow

npm run build          || { echo "tsc build failed."; exit 1; }
npm run plugin:build   || { echo "openclaw plugin:build failed."; exit 1; }
npm run plugin:validate || { echo "plugin validation failed."; exit 1; }

if [[ "$SKIP_INSTALL" != "--skip-install" ]]; then
    npm run plugin:install
    echo "Plugin installed. Restart OpenClaw to load the updated version."
else
    echo "Plugin built (skipped install). Run 'openclaw plugins install .' manually."
fi

cd ..
