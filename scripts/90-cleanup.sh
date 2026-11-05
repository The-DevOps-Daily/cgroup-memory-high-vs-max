#!/usr/bin/env bash
# Remove the data file and check that no cgroup or unit from this repo is left.
set -uo pipefail
cd "$(dirname "$0")/.."
rm -f work/data.bin && rmdir work 2>/dev/null
systemctl stop ddmemhigh.slice 2>/dev/null
echo "units left:";   systemctl list-units --all --no-legend 'ddmemhigh*' | sed 's/^/  /'
echo "cgroups left:"; find /sys/fs/cgroup -maxdepth 2 -name 'ddmemhigh*' | sed 's/^/  /'
