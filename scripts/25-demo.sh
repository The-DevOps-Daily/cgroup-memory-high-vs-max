#!/usr/bin/env bash
# A short, readable session for the post: the same workload under systemd's
# MemoryMax= alone, then under MemoryHigh= and MemoryMax= together. Run it
# after the matrix, not during it. Output: results/25-demo.txt
set -uo pipefail
cd "$(dirname "$0")/.."
python3 -I scripts/lib/workload.py --help > /dev/null   # warm the interpreter's page cache outside the scopes
w="python3 -I scripts/lib/workload.py --kind anon --target-mib 320 --progress"
{
  echo "# $(date -u +%FT%TZ) $(uname -r), $(systemctl --version | head -1)"
  echo "\$ systemd-run --scope -p MemoryMax=256M $w"
  systemd-run --scope --quiet --slice=ddmemhigh.slice -p MemoryMax=256M $w
  echo "exit status $?"
  echo "\$ systemd-run --scope -p MemoryHigh=241590272 -p MemoryMax=256M $w --max-seconds 30"
  systemd-run --scope --quiet --slice=ddmemhigh.slice -p MemoryHigh=241590272 -p MemoryMax=256M $w --max-seconds 30
  echo "exit status $?"
} > results/25-demo.txt 2>&1
cat results/25-demo.txt
