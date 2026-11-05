#!/usr/bin/env bash
# Show which cgroup v2 files systemd writes for MemoryMin=, MemoryLow=,
# MemoryHigh= and MemoryMax=. Each case is a transient scope that reads its
# own cgroup files and exits. Output: results/10-systemd-map.txt
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
show='cg=/sys/fs/cgroup$(sed -n "s/^0:://p" /proc/self/cgroup); echo "  cgroup $cg"; for f in memory.min memory.low memory.high memory.max memory.swap.max memory.oom.group; do echo "  $f $(cat $cg/$f)"; done'
run() {
  echo "\$ systemd-run --scope --slice=ddmemhigh.slice $* sh -c '<print memory files>'"
  systemd-run --scope --quiet --slice=ddmemhigh.slice "$@" sh -c "$show"
}
{
  echo "# $(date -u +%FT%TZ) $(systemctl --version | head -1)"
  run -p MemoryMin=16M -p MemoryLow=64M -p MemoryHigh=241590272 -p MemoryMax=256M
  run -p MemoryHigh=241590272
  run -p MemoryMax=256M
  run -p MemoryHigh=3% -p MemoryMax=infinity
} > results/10-systemd-map.txt 2>&1
cat results/10-systemd-map.txt
