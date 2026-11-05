# Claim, written before any run

Written 2026-11-05, before the first measurement. The predictions come from
`mm/memcontrol.c` in the Ubuntu kernel that the test host runs
(6.8.0-147.147, see `results/01-source-check.txt`). If a run disagrees, the
run wins and this file stays as it is.

## Claim

A workload that goes over `memory.high` is not killed. It slows down: the
latency of each allocation goes up sharply, its memory stays near the limit,
and the cgroup's PSI memory pressure shows the stall. With only `memory.max`,
the same workload runs at full speed until the kernel OOM-kills it.

The test host has no swap. So we expect this only for anonymous memory, which
the kernel cannot reclaim without swap. Page cache is different: the kernel can
drop clean file pages, so neither limit should throttle or kill a workload that
fills the page cache.

## Setup

- Limits: `memory.max` = 256 MiB (268435456 bytes). `memory.high` =
  241590272 bytes (230.4 MiB). That is the value the kubelet computes with
  MemoryQoS on, `limits.memory: 256Mi`, no memory request and the 1.36
  default throttling factor 0.9: floor(0.9 x 256 MiB / 4096) x 4096.
- Configurations: `none` (no limit on the run cgroup), `max` only, `high`
  only, `both`.
- Workloads (one script, `scripts/lib/workload.py`, seeded):
  - `anon-fit`: grow private anonymous memory in 256 KiB chunks (64 pages, one
    memcg charge batch) until it holds W1, then free one chunk and allocate
    one, 200 times. W1 is set from a smoke run so that `memory.current` sits
    about 5% above `memory.high` and below `memory.max`.
  - `anon-over`: the same, with a target of 320 MiB, above `memory.max`.
  - `anon-over-4p`: `anon-over` split over 4 processes in one cgroup
    (`high` only).
  - `file-over`: read 320 MiB of a 512 MiB file in 256 KiB reads, then 200
    random reads in that range. This fills the page cache, not anonymous
    memory.
- 3 repetitions of every run, 150 s cap per run.

## Predictions from the kernel source

Penalty per 64-page charge batch while over `memory.high`, after reclaim
fails (HZ=1000): `64000 x o^2` ms, where `o = (usage - high) / high`. No sleep
at 10 ms or less (o <= 1.25%), at most 2000 ms (`MEMCG_MAX_HIGH_DELAY_JIFFIES`).
Before it sleeps, the kernel calls `reclaim_high()` 17 times (1 + 16 retries),
and each call adds 1 to the `high` counter in `memory.events`.

| Run | Prediction |
| --- | --- |
| `anon-fit-none`, `anon-fit-max` | No kill. Same latency. `max` counter stays 0. |
| `anon-fit-high`, `anon-fit-both` | No kill. Each churn op sleeps once for about `64000 x o^2` ms: roughly 100 to 300 ms when usage is 3 to 6% over high, more than 100 times the `none` latency. `memory.current` stays above `memory.high`, because nothing is reclaimable. |
| `anon-over-max` | OOM kill when `memory.current` reaches 256 MiB. No latency rise before the kill. |
| `anon-over-high` | No kill in 150 s. Latency per op climbs with the overage and then flattens at about 2 s. `memory.current` keeps growing past `memory.high`, at about 128 KiB/s (64 pages per 2 s) once the penalty is at the cap. |
| `anon-over-both` | OOM kill at 256 MiB, but only after a throttled climb from 230 to 256 MiB that the formula puts at about 27 s. |
| `anon-over-4p` (high only) | The 2 s cap is per task, so 4 processes grow about 4 times faster than 1 in the capped region. |
| `file-over-*` | No kill in any configuration. `memory.current` stays at or below the limit. No over-high sleeps: latency changes come from cache misses (disk reads), not from throttling. |
| PSI | `memory.pressure` `some` total grows by about the time the workload spent stalled. With one task, `full` is close to `some`. |

## What would prove the claim wrong

- An anonymous run with only `memory.high` gets OOM-killed, or its latency
  does not go up (less than 10 times the `none` run).
- `memory.current` of an anonymous `high` run stays at or under
  `memory.high` (that would mean reclaim worked without swap).
- An `anon-over-max` run shows a latency rise well before the kill (p99 of the
  last 10% of ops more than 10 times the `none` p99).
- A single op sleeps much longer than 2 s per charge batch, or the measured
  delay is off from the formula by more than 2 times at the median.
- A page cache run under `memory.high` shows throttle sleeps like the
  anonymous runs.

## Added after the smoke runs, before the main matrix (2026-11-05, 11:25 UTC)

The smoke runs (`results/_smoke1` to `_smoke5`, older code, not used in the
summary) changed two things. We record them here before the main run, and the
original text above stays as it was.

1. **The penalty is paid per page, not per 64-page batch.** The `high` counter
   in `memory.events` rises by 17 per sleep (1 + `MAX_RECLAIM_RETRIES`), so the
   workload now reads it before and after every op. With page faults, one
   256 KiB op slept up to 64 times, once per page. Each sleep was close to the
   formula (measured / (sleeps x formula) had a median of 1.04 to 1.16). With
   `MAP_POPULATE` the same op slept about twice. A new charge only happens when
   the per-CPU precharge (`consume_stock`) is empty. We do not know what
   empties it during the sleep, and we did not trace it.
2. **File pages in the cgroup change everything.** In one smoke run, some of
   the interpreter's own file pages were charged to the run cgroup. Reclaim
   took them, the process faulted them back in, and it made no progress for
   65 s under `memory.high`. Under `memory.max` alone, the same thing happened
   without an OOM kill for 70 s. Because of this, every run now names its
   code mode: `warm` (the interpreter's pages are charged outside the run
   cgroup) or `own` (a fresh copy of the interpreter, read inside the run
   cgroup, like a container's first start). Every run's disk reads and writes
   are capped at 100 MiB/s with `io.max`. In the smoke runs the thrash read up
   to 500 MB/s from a shared disk. One run (`anon-over-max-owncode-fastdisk`,
   1 repetition) keeps the uncapped disk.

New predictions:

| Run | Prediction |
| --- | --- |
| `anon-fit-high`, `anon-fit-both` (warm) | 1 to 64 sleeps per throttled op; per-sleep time within 30% of the formula; no kill |
| `anon-fit-high-populate` | 3 or fewer sleeps per op; the run finishes its 200 churn ops in under 60 s |
| `anon-over-both` (warm) | Not killed within 150 s |
| `anon-over-both-long` (45 min cap, 1 run) | OOM kill after 10 to 45 minutes |
| `anon-fit-high-owncode`, `anon-over-both-owncode` | No kill in 20 s; `pgsteal` and file refaults keep rising; `memory.current` stays within 3% of `memory.high` |
| `anon-over-max-owncode` (100 MiB/s cap) | Thrashes at 256 MiB for more than 5 s before the OOM kill |
| `anon-over-max-owncode-fastdisk` | No OOM kill within 20 s |
| PSI | Memory `some` under-counts the own-code thrash (most of the time goes to disk reads) |

## Added after the main matrix (2026-11-05, 13:40 UTC)

A review after the main matrix found that `matrix.py` pins the driver to CPU 0
before it starts the workload, so every workload in `results/runs` shared CPU 0
with the 100 ms sampler. The clamp batch (`results/clamp`) and a diagnostic
batch (`results/diag`: workload on CPU 0 or CPU 2, sampler every 100 ms or 1 s)
ran after that, from commit 8b9a71b. We did not write predictions for the
diagnostic batch before it ran, so treat it as exploration, not as a test of a
prediction.
