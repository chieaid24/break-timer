#!/bin/bash
# Install the macOS menu bar app and start it at every sign-in.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv="$repo_root/.venv"
label="com.chieaid24.productivitytimer"
plist="$HOME/Library/LaunchAgents/$label.plist"

python_bin=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
            python_bin="$(command -v "$candidate")"
            break
        fi
    fi
done

if [ -z "$python_bin" ]; then
    echo "Python 3.11 or newer is required. Install it with: brew install python@3.12" >&2
    exit 1
fi

echo "Using $python_bin ($("$python_bin" -V))"

if [ ! -x "$venv/bin/python" ]; then
    "$python_bin" -m venv "$venv"
fi

"$venv/bin/python" -m pip install --upgrade --quiet pip
"$venv/bin/python" -m pip install --quiet -r "$repo_root/requirements-macos.txt"

# The app rewrites this file on every launch; writing it here lets launchd
# start the app for the first time.
"$venv/bin/python" - "$repo_root" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])

from productivity_timer.macos import (
    LaunchAgentRegistration,
    _launch_agent_path,
    _state_dir,
    launch_arguments,
    package_root,
)

state_dir = _state_dir()
state_dir.mkdir(parents=True, exist_ok=True)
LaunchAgentRegistration(
    launch_arguments(),
    package_root(),
    state_dir / "launchd.log",
    _launch_agent_path(),
).ensure()
print(f"Wrote {_launch_agent_path()}")
PY

launchctl bootout "gui/$UID/$label" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$plist"

echo
echo "Productivity Timer is running in the menu bar and will start at sign-in."
echo "Settings: ~/Library/Application Support/ProductivityTimer/settings.json"
echo "Remove it with: scripts/uninstall-macos.sh"
