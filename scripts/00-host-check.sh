#!/usr/bin/env bash
# Record the host facts the results depend on. Output: results/00-host.txt
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
{
  echo "# $(date -u +%FT%TZ)"
  echo "## kernel";       uname -r; cat /proc/version_signature 2>/dev/null
  echo "## os";           grep PRETTY_NAME /etc/os-release
  echo "## systemd";      systemctl --version | head -1
  echo "## python";       python3 --version
  echo "## cpus";         nproc
  echo "## memory";       grep -E '^(MemTotal|MemAvailable|SwapTotal):' /proc/meminfo
  echo "## swap devices"; cat /proc/swaps
  echo "## zswap";        cat /sys/module/zswap/parameters/enabled 2>/dev/null || echo "no zswap module"
  echo "## cgroup fs";    stat -fc %T /sys/fs/cgroup
  echo "## root cgroup.controllers"; cat /sys/fs/cgroup/cgroup.controllers
  echo "## PSI";          ls /proc/pressure/ && cat /proc/pressure/memory
  echo "## CONFIG_HZ and memcg/PSI config"
  grep -E '^CONFIG_(HZ|MEMCG|PSI)[=_]' "/boot/config-$(uname -r)" 2>/dev/null
  echo "## transparent hugepages"; cat /sys/kernel/mm/transparent_hugepage/enabled
  echo "## vm";           for f in overcommit_memory swappiness; do echo "$f $(cat /proc/sys/vm/$f)"; done
  echo "## page size";    getconf PAGESIZE
} > results/00-host.txt 2>&1
cat results/00-host.txt
