#!/usr/bin/env bash
# Run the matrix in scripts/lib/matrix.py inside a transient systemd scope.
# Delegate=yes hands the scope's cgroup subtree to the script; MemoryMax=1G
# caps everything the runs do, whatever happens inside.
# Usage: scripts/20-run-matrix.sh [--reps N] [--only name,name] [--out DIR]
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs ] || { echo "needs cgroup v2" >&2; exit 1; }
[ -f work/data.bin ] || { echo "run scripts/15-make-file.sh first" >&2; exit 1; }
unit="ddmemhigh-$(date -u +%Y%m%dT%H%M%SZ)"
exec systemd-run --scope --quiet --unit="$unit" --slice=ddmemhigh.slice \
  -p Delegate=yes -p MemoryMax=1G \
  python3 -I scripts/lib/matrix.py "$@"
