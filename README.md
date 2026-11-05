# cgroup-memory-high-vs-max

```bash
# on a Linux host with cgroup v2, systemd and root (or a delegated cgroup subtree)
scripts/00-host-check.sh && scripts/10-systemd-map.sh && scripts/15-make-file.sh
scripts/20-run-matrix.sh --reps 3                                            # about 46 minutes
scripts/20-run-matrix.sh --reps 1 --only anon-over-both-long                 # up to 45 minutes
scripts/20-run-matrix.sh --out results/clamp --reps 3 --only anon-clamp-high # about 3 minutes
scripts/20-run-matrix.sh --out results/diag --reps 3 --only diag-over-high-cpu0-100ms,diag-over-high-cpu2-100ms,diag-over-high-cpu0-1s,diag-over-high-cpu2-1s,diag-over-both-cpu2-1s,diag-fit-high-cpu2-1s
scripts/25-demo.sh && scripts/90-cleanup.sh && scripts/91-redact-host.sh "$(hostname)"
# anywhere with Python 3 and git
scripts/01-source-check.sh && scripts/30-summarize.py && scripts/40-predict.py && scripts/50-charts.py
```

The same allocating workload runs under no limit, `memory.max` only, `memory.high` only and both, and the repo records what the kernel does: per-operation latency, `memory.current`, `memory.events`, PSI, reclaim counters and disk reads. The question is the one in the systemd and kernel docs: `memory.high` throttles, `memory.max` kills. How much does it throttle, and when does the kill come?

It needs a cgroup v2 Linux host where you can create cgroups: root, or a subtree delegated to your user. The scripts never set a limit above 1 GiB, cap each run's disk I/O at 100 MiB/s (one variant excepted), and work only inside a transient scope in `ddmemhigh.slice`. The claim and what would prove it wrong are in [CLAIM.md](CLAIM.md), written before the first run. A second part was added after the smoke runs, before the main matrix, and a third after all runs, which says that the clamp and diagnostic batches had no predictions written in advance.

## What each script does

| Script | Where | What it records |
| --- | --- | --- |
| `scripts/00-host-check.sh` | host | Kernel, systemd, swap, zswap, THP, `CONFIG_HZ`, PSI, Docker and runc versions, Docker's memory flags. `results/00-host.txt` |
| `scripts/01-source-check.sh` | anywhere | The upstream lines this repo relies on, at pinned commits: the over-high penalty in the Ubuntu 6.8.0-147 kernel, systemd v255 docs, runc 1.5.2 and Docker 29.9.3 memory mapping, Kubernetes v1.36.6 and v1.37.2 MemoryQoS, KEP-2570. `results/01-source-check.txt` |
| `scripts/10-systemd-map.sh` | host | Which cgroup files `MemoryMin=`, `MemoryLow=`, `MemoryHigh=` and `MemoryMax=` write, read back from inside transient scopes. `results/10-systemd-map.txt` |
| `scripts/15-make-file.sh` | host | A 512 MiB data file for the page cache runs. `results/15-data-file.txt` |
| `scripts/20-run-matrix.sh` | host | Starts `scripts/lib/matrix.py` in a transient scope with `Delegate=yes` and `MemoryMax=1G`. For every run it makes a child cgroup, writes the limits, starts `scripts/lib/workload.py` in it and samples the cgroup files every 100 ms from outside. `results/<batch>/<run>/{meta.json,ops.jsonl,samples.jsonl,final.json}` |
| `scripts/lib/workload.py` | host | The workload: 256 KiB private anonymous chunks (or 256 KiB file reads), seeded with mulberry32, one JSON line per op with its latency, `memory.current` and the rise in the `high` and `max` counters. |
| `scripts/25-demo.sh` | host | A short session through systemd's own `MemoryMax=` and `MemoryHigh=`. `results/25-demo.txt` |
| `scripts/30-summarize.py` | anywhere | Per-run and per-config tables. Refuses incomplete runs, a batch with mixed code stamps, and stamps that match no commit. `results/summary.{md,json}` |
| `scripts/40-predict.py` | anywhere | A port of the kernel's penalty formula, compared with every throttled op, the 2 s cap, the time to the OOM kill, PSI and 1 vs 4 processes. `results/predict.{md,json}` |
| `scripts/50-charts.py` | anywhere | The chart data in the post. `results/charts.json` |
| `scripts/90-cleanup.sh` | host | Removes the data file and checks that no unit or cgroup from this repo is left. |
| `scripts/91-redact-host.sh` | anywhere | Replaces the host name with `testhost` in the recorded files before they are published. |

## The runs

`warm` runs start the interpreter once in the driver cgroup before the run (`workload.py --help`), so its code pages are already cached and charged outside the run cgroup, and the run cgroup holds only what the workload allocates. `pgsteal` stayed 0 in every warm anonymous run: there was nothing to reclaim. `own` runs exec a fresh copy of the interpreter that is not in the page cache, so its code pages are charged to the run cgroup, as for a container on its first start. `memory.high` is 241590272 bytes (230.4 MiB) everywhere: what the kubelet computes with MemoryQoS for `limits.memory: 256Mi`, `requests.memory: 0` and throttling factor 0.9 (an omitted request defaults to the limit, and then the kubelet writes no `memory.high`). `memory.max` is 256 MiB.

`results/_smoke1` to `results/_smoke5` are the smoke runs made with earlier code. The summary does not use them; `CLAIM.md` says what they changed.

## Results

Full tables: [results/summary.md](results/summary.md) and [results/predict.md](results/predict.md). Host: Ubuntu 24.04, kernel 6.8.0-147-generic, systemd 255, 4 vCPU, 7.75 GiB, no swap, `CONFIG_HZ=1000`. `memory.max` = 256 MiB, `memory.high` = 230.4 MiB.

| Run (warm code, 3 repetitions unless noted; workload on CPU 0 with the sampler, see below) | Outcome | Numbers |
| --- | --- | --- |
| asks for 320 MiB, `memory.max` only | OOM kill 3 of 3 | killed 0.28 to 0.39 s after start; p99 of the last 10% of ops 0.29 to 0.41 ms |
| asks for 320 MiB, `memory.high` only | not killed in 150 s | 241.5 to 242.2 MiB at the cap, growing 25 to 30 KiB/s; median 10.3 s per 256 KiB op at 241 MiB |
| needs 239 MiB, `memory.max` only | done | median churn op 0.277 ms (no limit: 0.257 ms) |
| needs 239 MiB, `memory.high` only | not killed in 150 s | median churn op 6,216 ms; 15 to 17 of 200 churn ops done |
| same, `MAP_POPULATE` | done in about 41 s | 2 sleeps per op, median churn op 191.8 ms |
| asks for 320 MiB, both limits | not killed in 150 s | 241.7 to 242.0 MiB at the cap |
| asks for 320 MiB, 4 processes, `memory.high` | not killed in 150 s | 249.1 to 250.8 MiB at the cap |
| asks for 320 MiB, both limits, 45 min cap, 1 run | OOM kill after 1,747.7 s (29.1 min) | formula with one sleep per page predicted 1,720 s; with one per 64 pages, 27 s |
| grows to 300 MiB, then `memory.high` set so usage is 33.3% over it | not killed in 40 s | median sleep 2,047.9 ms: the 2,000 ms cap rounded up to the timer wheel's 64 ms step |

**The shared CPU.** `matrix.py` pins the driver to CPU 0 before it starts the workload, so every workload in `results/runs` inherited CPU 0 and shared it with the sampler, which wakes every 100 ms and allocates in its own cgroup. That empties the workload's per-CPU precharge, so a throttled task pays a new sleep for almost every page. `results/diag` measures this: the workload on CPU 0 or CPU 2 (`--cpu 2`), the sampler every 100 ms or 1 s. Read the matrix numbers for `memory.high` as "next to a busy neighbour".

- Time per sleep: measured / (sleeps x kernel formula) has a median of 1.08 to 1.10 in every single-process matrix run; 97% to 100% of throttled ops are within 30%. Half a timer-wheel step per sleep explains part of the excess (1.030 to 1.055 for sleeps of 64 ms or more).
- Sleeps per 64-page op when the formula's sleep is 50 ms or more: median 64 (one per page) in the matrix and with the sampler on the same CPU at 100 ms; median 1 or 2 with the workload on CPU 2 or the sampler at 1 s, but with phases of 64 that took 46% to 72% of the throttled time. With `MAP_POPULATE`: 2 (3 in 8 of 600 churn ops).
- Needs 239 MiB, `memory.high` only, workload on CPU 2, sampler at 1 s: median churn op 191.8 ms in 3 of 3 runs (about 750 times the no-limit median, against about 24,000 times in the matrix); all 200 churn ops done in 2 of 3 runs within 120 s.
- Asks for 320 MiB, both limits, workload on CPU 2, sampler at 1 s: not killed within 120 s in 3 of 3 runs; 240.8 to 254.4 MiB at the cap.
- PSI memory `some` total matches the ops' time over baseline (ratio 1.003 to 1.068). The throttled task is in state `D` in `mem_cgroup_handle_over_high` in 98% to 99% of samples.
- Own code charged to the cgroup (20 s cap, disk at 100 MiB/s): under `memory.high` and both, stuck at 230.2 to 230.4 MiB; under `memory.max` only, held 255.9 MiB with 19,140 to 20,019 `max` events and no OOM kill in 3 of 3; 2.4 to 2.6 GB read from disk per run; memory PSI `some` 8% under `memory.max`, io PSI `some` 85%. Uncapped disk: 10,483 MB read in 25 s, not killed.
- Page cache (`file-over-*`): not killed and not throttled in any of 12 runs.
- systemd 255 writes `MemoryMin/Low/High/Max=` to `memory.min/low/high/max` as given ([results/10-systemd-map.txt](results/10-systemd-map.txt)). Docker 29.9.3 writes `--memory` to `memory.max` and `--memory-reservation` to `memory.low` through runc 1.5.2, and has no flag for `memory.high`. Kubernetes 1.36: MemoryQoS alpha, off by default, factor 0.9. Kubernetes 1.37: beta, on by default, factor unset, so no `memory.high` unless you set it ([results/01-source-check.txt](results/01-source-check.txt)).

## What this does not show

- One host, one kernel, no swap. With swap or zswap, both limits can behave differently. Newer kernels changed the memcg charge code.
- What empties the per-CPU precharge was read from the source, not traced. Besides our sampler, other work on the shared host did it in phases.
- The own-code runs were stopped after 20 s because they read about 100 MB/s from a shared disk, so we do not know how long the thrash lasts before an OOM kill.
- The workload is a Python loop. Other runtimes touch memory differently, and the `MAP_POPULATE` run shows that the touch pattern changes the cost.
- `memory.events` counts the whole cgroup, so the 4-process run is used for growth only.
- No kubelet ran here. The Kubernetes rows are from source.
- The host name in `meta.json` and in the kernel log lines is replaced with `testhost` (`scripts/91-redact-host.sh`).

## License

MIT
