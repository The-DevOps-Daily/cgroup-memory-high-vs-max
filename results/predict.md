# Kernel formula vs measured

Baseline op latency (median p50 of `anon-fit-none`): 0.225 ms. Formula: see the header of `scripts/40-predict.py`.

## 1. Time per sleep: measured / (sleeps x formula)

| run | ops checked | p10 | p50 | p90 | within 30% | ops with partial rounds |
| --- | --- | --- | --- | --- | --- | --- |
| diag-fit-high-cpu2-1s-r1 | 223 | 1.019 | 1.042 | 1.072 | 100% | 12 |
| diag-fit-high-cpu2-1s-r2 | 223 | 1.019 | 1.042 | 1.066 | 100% | 12 |
| diag-fit-high-cpu2-1s-r3 | 145 | 1.019 | 1.053 | 1.078 | 100% | 12 |
| diag-over-both-cpu2-1s-r1 | 44 | 1.037 | 1.063 | 1.142 | 100% | 12 |
| diag-over-both-cpu2-1s-r2 | 29 | 1.087 | 1.105 | 1.236 | 100% | 13 |
| diag-over-both-cpu2-1s-r3 | 83 | 1.021 | 1.048 | 1.099 | 100% | 12 |
| diag-over-high-cpu0-100ms-r1 | 33 | 1.063 | 1.091 | 1.130 | 100% | 13 |
| diag-over-high-cpu0-100ms-r2 | 32 | 1.070 | 1.097 | 1.135 | 100% | 12 |
| diag-over-high-cpu0-100ms-r3 | 32 | 1.073 | 1.097 | 1.143 | 100% | 12 |
| diag-over-high-cpu0-1s-r1 | 62 | 1.028 | 1.055 | 1.095 | 100% | 12 |
| diag-over-high-cpu0-1s-r2 | 66 | 1.024 | 1.053 | 1.102 | 100% | 12 |
| diag-over-high-cpu0-1s-r3 | 67 | 1.026 | 1.050 | 1.107 | 100% | 12 |
| diag-over-high-cpu2-100ms-r1 | 68 | 1.021 | 1.049 | 1.095 | 100% | 12 |
| diag-over-high-cpu2-100ms-r2 | 67 | 1.023 | 1.053 | 1.105 | 100% | 12 |
| diag-over-high-cpu2-100ms-r3 | 74 | 1.022 | 1.048 | 1.105 | 100% | 12 |
| diag-over-high-cpu2-1s-r1 | 41 | 1.036 | 1.074 | 1.114 | 100% | 12 |
| diag-over-high-cpu2-1s-r2 | 66 | 1.024 | 1.043 | 1.148 | 100% | 13 |
| diag-over-high-cpu2-1s-r3 | 77 | 1.023 | 1.052 | 1.105 | 100% | 12 |
| anon-fit-both-r1 | 37 | 1.078 | 1.094 | 1.140 | 100% | 13 |
| anon-fit-both-r2 | 40 | 1.074 | 1.087 | 1.128 | 100% | 12 |
| anon-fit-both-r3 | 40 | 1.071 | 1.091 | 1.155 | 100% | 12 |
| anon-fit-high-populate-r1 | 223 | 1.043 | 1.089 | 1.089 | 99% | 12 |
| anon-fit-high-populate-r2 | 222 | 1.043 | 1.087 | 1.099 | 97% | 11 |
| anon-fit-high-populate-r3 | 223 | 1.043 | 1.088 | 1.089 | 98% | 12 |
| anon-fit-high-r1 | 40 | 1.057 | 1.081 | 1.168 | 100% | 12 |
| anon-fit-high-r2 | 37 | 1.056 | 1.091 | 1.182 | 100% | 12 |
| anon-fit-high-r3 | 40 | 1.056 | 1.088 | 1.156 | 100% | 12 |
| anon-over-both-long-r1 | 91 | 1.038 | 1.063 | 1.121 | 99% | 12 |
| anon-over-both-r1 | 34 | 1.059 | 1.085 | 1.132 | 100% | 13 |
| anon-over-both-r2 | 33 | 1.072 | 1.097 | 1.128 | 100% | 13 |
| anon-over-both-r3 | 35 | 1.069 | 1.095 | 1.129 | 100% | 12 |
| anon-over-high-r1 | 36 | 1.065 | 1.088 | 1.131 | 100% | 12 |
| anon-over-high-r2 | 32 | 1.063 | 1.096 | 1.185 | 100% | 13 |
| anon-over-high-r3 | 35 | 1.059 | 1.088 | 1.136 | 100% | 12 |

Same ratio with half a timer-wheel step added to each sleep (1 ms step under 64 ms, 8 ms from 64 to 511 ms):

| run | under 64 ms | 64 ms or more |
| --- | --- | --- |
| diag-fit-high-cpu2-1s-r1 | 1.059 | 0.998 |
| diag-fit-high-cpu2-1s-r2 | 1.068 | 0.998 |
| diag-fit-high-cpu2-1s-r3 | 1.052 | 1.008 |
| diag-over-both-cpu2-1s-r1 | 1.084 | 1.025 |
| diag-over-both-cpu2-1s-r2 | 1.094 | 1.054 |
| diag-over-both-cpu2-1s-r3 | 1.053 | 1.017 |
| diag-over-high-cpu0-100ms-r1 | 1.066 | 1.056 |
| diag-over-high-cpu0-100ms-r2 | 1.073 | 1.056 |
| diag-over-high-cpu0-100ms-r3 | 1.073 | 1.056 |
| diag-over-high-cpu0-1s-r1 | 1.052 | 1.025 |
| diag-over-high-cpu0-1s-r2 | 1.064 | 1.026 |
| diag-over-high-cpu0-1s-r3 | 1.052 | 1.024 |
| diag-over-high-cpu2-100ms-r1 | 1.047 | 1.022 |
| diag-over-high-cpu2-100ms-r2 | 1.054 | 1.020 |
| diag-over-high-cpu2-100ms-r3 | 1.055 | 1.017 |
| diag-over-high-cpu2-1s-r1 | 1.069 | 1.034 |
| diag-over-high-cpu2-1s-r2 | 1.113 | 1.018 |
| diag-over-high-cpu2-1s-r3 | 1.060 | 1.024 |
| anon-fit-both-r1 | 1.091 | 1.042 |
| anon-fit-both-r2 | 1.071 | 1.039 |
| anon-fit-both-r3 | 1.080 | 1.042 |
| anon-fit-high-populate-r1 | 1.054 | 1.041 |
| anon-fit-high-populate-r2 | 1.081 | 1.039 |
| anon-fit-high-populate-r3 | 1.058 | 1.041 |
| anon-fit-high-r1 | 1.076 | 1.030 |
| anon-fit-high-r2 | 1.085 | 1.042 |
| anon-fit-high-r3 | 1.072 | 1.041 |
| anon-over-both-long-r1 | 1.067 | 1.034 |
| anon-over-both-r1 | 1.072 | 1.042 |
| anon-over-both-r2 | 1.085 | 1.055 |
| anon-over-both-r3 | 1.076 | 1.051 |
| anon-over-high-r1 | 1.069 | 1.051 |
| anon-over-high-r2 | 1.088 | 1.046 |
| anon-over-high-r3 | 1.066 | 1.050 |

## 1b. Sleeps per 256 KiB op (64 pages), by the formula's sleep length

One-process warm runs that touch memory with page faults (not `--populate`), ops whose rise in `high` is a multiple of 17. 64 or more means one sleep per page. `matrix`: all such runs in results/runs, where the workload inherited the driver's CPU 0 and the driver sampled every 100 ms. `diag-*`: results/diag.

| group | sleep length | ops | sleeps p10 | sleeps p50 | ops with 64 or more |
| --- | --- | --- | --- | --- | --- |
| diag-fit-high-cpu2-1s | 11 to 25 ms | 19 | 1 | 1 | 26% |
| diag-fit-high-cpu2-1s | 25 to 50 ms | 23 | 1 | 1 | 0% |
| diag-fit-high-cpu2-1s | 50 to 100 ms | 549 | 2 | 2 | 4% |
| diag-over-both-cpu2-1s | 11 to 25 ms | 18 | 1 | 44 | 44% |
| diag-over-both-cpu2-1s | 25 to 50 ms | 21 | 1 | 64 | 57% |
| diag-over-both-cpu2-1s | 50 to 100 ms | 33 | 1 | 3 | 33% |
| diag-over-both-cpu2-1s | 100 to 200 ms | 35 | 1 | 4 | 31% |
| diag-over-both-cpu2-1s | 200 to 400 ms | 26 | 1 | 3 | 4% |
| diag-over-both-cpu2-1s | 400 to 2001 ms | 23 | 1 | 3 | 0% |
| diag-over-high-cpu0-100ms | 11 to 25 ms | 21 | 1 | 1 | 0% |
| diag-over-high-cpu0-100ms | 25 to 50 ms | 21 | 1 | 2 | 0% |
| diag-over-high-cpu0-100ms | 50 to 100 ms | 33 | 47 | 64 | 88% |
| diag-over-high-cpu0-100ms | 100 to 200 ms | 22 | 64 | 64 | 100% |
| diag-over-high-cpu0-1s | 11 to 25 ms | 18 | 1 | 1 | 0% |
| diag-over-high-cpu0-1s | 25 to 50 ms | 21 | 1 | 1 | 0% |
| diag-over-high-cpu0-1s | 50 to 100 ms | 33 | 1 | 1 | 0% |
| diag-over-high-cpu0-1s | 100 to 200 ms | 48 | 1 | 1 | 0% |
| diag-over-high-cpu0-1s | 200 to 400 ms | 63 | 1 | 3 | 6% |
| diag-over-high-cpu0-1s | 400 to 2001 ms | 12 | 4 | 10 | 8% |
| diag-over-high-cpu2-100ms | 11 to 25 ms | 18 | 1 | 1 | 0% |
| diag-over-high-cpu2-100ms | 25 to 50 ms | 24 | 1 | 1 | 0% |
| diag-over-high-cpu2-100ms | 50 to 100 ms | 30 | 1 | 1 | 0% |
| diag-over-high-cpu2-100ms | 100 to 200 ms | 46 | 1 | 1 | 20% |
| diag-over-high-cpu2-100ms | 200 to 400 ms | 64 | 1 | 2 | 0% |
| diag-over-high-cpu2-100ms | 400 to 2001 ms | 27 | 1 | 3 | 4% |
| diag-over-high-cpu2-1s | 11 to 25 ms | 18 | 1 | 1 | 33% |
| diag-over-high-cpu2-1s | 25 to 50 ms | 22 | 1 | 6 | 27% |
| diag-over-high-cpu2-1s | 50 to 100 ms | 33 | 1 | 1 | 30% |
| diag-over-high-cpu2-1s | 100 to 200 ms | 45 | 1 | 1 | 0% |
| diag-over-high-cpu2-1s | 200 to 400 ms | 44 | 1 | 2 | 9% |
| diag-over-high-cpu2-1s | 400 to 2001 ms | 22 | 1 | 3 | 0% |
| matrix | 11 to 25 ms | 83 | 1 | 2 | 24% |
| matrix | 25 to 50 ms | 95 | 2 | 7 | 23% |
| matrix | 50 to 100 ms | 228 | 64 | 64 | 92% |
| matrix | 100 to 200 ms | 73 | 64 | 64 | 100% |
| matrix | 200 to 400 ms | 22 | 64 | 64 | 100% |
| matrix | 400 to 2001 ms | 29 | 64 | 64 | 100% |

## 1c. Sleeps per op when the formula's sleep is 50 ms or more, per group

Time share: of the seconds these ops took, the share spent in ops that slept 32 or more times.

| group | ops | sleeps p50 | ops with 64 or more | op seconds | time share, 32 or more sleeps |
| --- | --- | --- | --- | --- | --- |
| diag-fit-high-cpu2-1s | 549 | 2 | 4% | 311.3 | 59% |
| diag-over-both-cpu2-1s | 117 | 3 | 20% | 320.0 | 72% |
| diag-over-high-cpu0-100ms | 55 | 64 | 93% | 348.7 | 100% |
| diag-over-high-cpu0-1s | 156 | 2 | 3% | 346.0 | 46% |
| diag-over-high-cpu2-100ms | 167 | 1 | 6% | 325.7 | 53% |
| diag-over-high-cpu2-1s | 144 | 1 | 10% | 299.1 | 72% |
| matrix | 352 | 64 | 95% | 3420.1 | 100% |

## 2. The 2 s cap (`MEMCG_MAX_HIGH_DELAY_JIFFIES`)

| run | memory.high set at MiB | over high | formula without cap, ms | ops | sleeps per op | per sleep p50 ms | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| anon-clamp-high-r1 | 307.2 | 33.3% | 7106 | 10 | [1, 2] | 2047.9 | 2047.3 | 2064.9 |
| anon-clamp-high-r2 | 307.2 | 33.3% | 7108 | 10 | [1, 2] | 2047.9 | 2021.8 | 2048.0 |
| anon-clamp-high-r3 | 307.2 | 33.3% | 7107 | 10 | [1, 2] | 2047.9 | 2011.7 | 2047.9 |

## 3. Time to the OOM kill, memory.high = 90% of memory.max

- anon-over-both-long-r1: throttling starts at 0.3 s (233.43 MiB). Outcome oom_kill, killed after 1747.69 s (1747.4 s after throttling started). Predicted from that point: 27.1 s with one sleep per 64 pages, 1720.2 s with one sleep per page.

## 4. PSI memory `some` total vs op time over baseline

| run | PSI some s | PSI full s | op time over baseline s | ratio |
| --- | --- | --- | --- | --- |
| diag-fit-high-cpu2-1s-r1 | 82.24 | 82.24 | 82.35 | 0.999 |
| diag-fit-high-cpu2-1s-r2 | 119.33 | 119.33 | 118.56 | 1.007 |
| diag-fit-high-cpu2-1s-r3 | 124.52 | 124.52 | 118.94 | 1.047 |
| diag-over-both-cpu2-1s-r1 | 119.77 | 119.77 | 119.94 | 0.999 |
| diag-over-both-cpu2-1s-r2 | 124.46 | 124.46 | 123.66 | 1.006 |
| diag-over-both-cpu2-1s-r3 | 123.69 | 123.69 | 123.53 | 1.001 |
| diag-over-high-cpu0-100ms-r1 | 124.09 | 124.09 | 122.12 | 1.016 |
| diag-over-high-cpu0-100ms-r2 | 124.26 | 124.26 | 115.31 | 1.078 |
| diag-over-high-cpu0-100ms-r3 | 124.21 | 124.21 | 115.53 | 1.075 |
| diag-over-high-cpu0-1s-r1 | 124.65 | 124.65 | 117.89 | 1.057 |
| diag-over-high-cpu0-1s-r2 | 120.59 | 120.59 | 120.69 | 0.999 |
| diag-over-high-cpu0-1s-r3 | 124.66 | 124.66 | 108.69 | 1.147 |
| diag-over-high-cpu2-100ms-r1 | 124.28 | 124.28 | 107.12 | 1.16 |
| diag-over-high-cpu2-100ms-r2 | 124.17 | 124.17 | 99.84 | 1.244 |
| diag-over-high-cpu2-100ms-r3 | 119.87 | 119.87 | 120.21 | 0.997 |
| diag-over-high-cpu2-1s-r1 | 124.64 | 124.64 | 112.28 | 1.11 |
| diag-over-high-cpu2-1s-r2 | 124.64 | 124.64 | 96.95 | 1.286 |
| diag-over-high-cpu2-1s-r3 | 120.4 | 120.4 | 120.53 | 0.999 |
| anon-fit-both-r1 | 153.72 | 153.72 | 153.19 | 1.003 |
| anon-fit-both-r2 | 152.21 | 152.21 | 151.7 | 1.003 |
| anon-fit-both-r3 | 153.55 | 153.55 | 153.05 | 1.003 |
| anon-fit-high-populate-r1 | 40.63 | 40.63 | 39.22 | 1.036 |
| anon-fit-high-populate-r2 | 40.81 | 40.81 | 39.4 | 1.036 |
| anon-fit-high-populate-r3 | 40.21 | 40.21 | 38.86 | 1.035 |
| anon-fit-high-r1 | 151.79 | 151.79 | 151.15 | 1.004 |
| anon-fit-high-r2 | 154.18 | 154.18 | 149.25 | 1.033 |
| anon-fit-high-r3 | 154.07 | 154.07 | 148.41 | 1.038 |
| anon-fit-max-r1 | 0.0 | 0.0 | 0.04 | None |
| anon-fit-max-r2 | 0.0 | 0.0 | 0.04 | None |
| anon-fit-max-r3 | 0.0 | 0.0 | 0.03 | None |
| anon-over-both-long-r1 | 1742.45 | 1742.45 | 1746.24 | 0.998 |
| anon-over-both-r1 | 153.5 | 153.5 | 151.19 | 1.015 |
| anon-over-both-r2 | 154.11 | 154.11 | 147.27 | 1.046 |
| anon-over-both-r3 | 154.11 | 154.11 | 144.63 | 1.066 |
| anon-over-high-r1 | 153.22 | 153.22 | 152.08 | 1.007 |
| anon-over-high-r2 | 154.18 | 154.18 | 145.33 | 1.061 |
| anon-over-high-r3 | 154.24 | 154.24 | 144.47 | 1.068 |
| anon-over-max-r1 | 0.0 | 0.0 | 0.06 | None |
| anon-over-max-r2 | 0.0 | 0.0 | 0.02 | None |
| anon-over-max-r3 | 0.0 | 0.0 | 0.01 | None |

## 5. Growth at the time cap: measured vs one sleep per 4 KiB page per process

Predicted growth = processes x 4 KiB / formula sleep at the last memory.current. Per repetition.

| config | processes | last memory.current MiB | measured KiB/s | predicted KiB/s |
| --- | --- | --- | --- | --- |
| anon-over-high | 1 | [242.2, 241.5, 242.0] | [25.29, 29.91, 26.62] | [24.0, 27.0, 24.7] |
| anon-over-both | 1 | [242.0, 241.7, 242.0] | [26.89, 27.96, 26.62] | [24.7, 26.1, 24.7] |
| anon-over-4p-high | 4 | [249.1, 250.8, 249.6] | [42.28, 34.04, 39.43] | [38.0, 31.9, 36.0] |
