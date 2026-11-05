#!/usr/bin/env bash
# Replace the test host's name with "testhost" in the recorded files before
# they are published. The name appears in os.uname() (meta.json) and in kernel
# log lines (final.json). Usage: scripts/91-redact-host.sh <hostname>
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?usage: $0 <hostname>}"
{ grep -rlF -- "$name" results || true; } | while read -r f; do sed -i "s/$name/testhost/g" "$f"; done
left=$(grep -rlF -- "$name" results | wc -l || true)
echo "files still containing the name: $left"
