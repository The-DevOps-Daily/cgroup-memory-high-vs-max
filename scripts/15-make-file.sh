#!/usr/bin/env bash
# Write the 512 MiB data file that the page cache runs read: one seeded
# 1 MiB block repeated. It is written inside a capped scope, synced, and then
# dropped from the page cache, so the first read in a run comes from disk.
# Output: work/data.bin and results/15-data-file.txt
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p work results
systemd-run --scope --quiet --slice=ddmemhigh.slice -p MemoryMax=1G python3 -I - <<'PY'
import hashlib, os, random
rng = random.Random(42)
block = bytes(rng.getrandbits(8) for _ in range(1 << 20))
h = hashlib.sha256()
fd = os.open("work/data.bin", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
for _ in range(512):
    os.write(fd, block)
    h.update(block)
os.fsync(fd)
os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
os.close(fd)
with open("results/15-data-file.txt", "w") as f:
    f.write(f"work/data.bin {os.path.getsize('work/data.bin')} bytes sha256 {h.hexdigest()}\n")
PY
cat results/15-data-file.txt
