#!/bin/bash
# Stop the macOS menu bar app and remove its sign-in entry.
# Pass --purge to also delete settings, logs, and reminder state.
set -euo pipefail

label="com.chieaid24.productivitytimer"
plist="$HOME/Library/LaunchAgents/$label.plist"
state_dir="$HOME/Library/Application Support/ProductivityTimer"

launchctl bootout "gui/$UID/$label" 2>/dev/null || true
rm -f "$plist"
echo "Removed the sign-in entry."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$state_dir"
    echo "Removed $state_dir"
else
    echo "Settings and logs are still in $state_dir (delete them with --purge)."
fi
