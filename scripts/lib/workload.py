#!/usr/bin/env python3
"""Allocate memory in 256 KiB steps and record the latency of every step.

--kind anon: private anonymous mmap chunks, each written in full. A chunk is
  64 pages, which is one memcg charge batch (MEMCG_CHARGE_BATCH).
--kind file: 256 KiB reads from --file, which fill the page cache.

Phases: "g" (grow) until the workload holds --target-mib, then "c" (churn)
for --churn-ops ops. anon churn frees one random chunk and allocates a new
one; file churn reads a random chunk that it read before. Every anon op also
copies one random held chunk, so the working set stays in use.

Output: one JSON line per op on stdout, or one readable line per second with
--progress. The random choices and the payload come from --seed (mulberry32).
"""
import argparse
import ctypes
import json
import mmap
import os
import sys
import time

CHUNK = 256 * 1024
MASK = 0xFFFFFFFF


def mulberry32(seed):
    state = seed & MASK

    def imul(a, b):
        return (a * b) & MASK

    def nxt():
        nonlocal state
        state = (state + 0x6D2B79F5) & MASK
        t = imul(state ^ (state >> 15), 1 | state)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & MASK) ^ t
        return ((t ^ (t >> 14)) & MASK) / 4294967296

    return nxt


def own_cgroup():
    with open("/proc/self/cgroup") as f:
        for line in f:
            if line.startswith("0::"):
                return "/sys/fs/cgroup" + line[3:].strip()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["anon", "file"], required=True)
    ap.add_argument("--target-mib", type=int, required=True)
    ap.add_argument("--churn-ops", type=int, default=200)
    ap.add_argument("--max-seconds", type=float, default=150.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--file", help="data file for --kind file")
    ap.add_argument("--cgroup", help="cgroup dir to read memory.current from (default: own)")
    ap.add_argument("--proc", type=int, default=0, help="process index, copied into every record")
    ap.add_argument("--progress", action="store_true", help="one readable line per second")
    ap.add_argument("--populate", action="store_true",
                    help="anon: MAP_POPULATE, so the kernel charges a chunk in one mmap call")
    ap.add_argument("--cpu", type=int, help="pin this process to one CPU")
    a = ap.parse_args()
    if a.cpu is not None:
        os.sched_setaffinity(0, {a.cpu})

    rnd = mulberry32(a.seed)
    page = bytes(int(rnd() * 256) for _ in range(4096))
    payload = page * (CHUNK // 4096)
    scratch = bytearray(CHUNK)
    smv = memoryview(scratch)

    cg = a.cgroup or own_cgroup()
    cur_fd = os.open(os.path.join(cg, "memory.current"), os.O_RDONLY)

    ev_fd = os.open(os.path.join(cg, "memory.events"), os.O_RDONLY)
    getcpu = ctypes.CDLL(None).sched_getcpu

    def current():
        return int(os.pread(cur_fd, 32, 0))

    def high_max():
        f = dict(line.split() for line in os.pread(ev_fd, 512, 0).decode().splitlines())
        return int(f["high"]), int(f["max"])

    flags = mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS | (mmap.MAP_POPULATE if a.populate else 0)
    fd = os.open(a.file, os.O_RDONLY) if a.kind == "file" else None
    held = []  # anon: mmap objects; file: offsets already read
    next_off = 0
    target = a.target_mib * 1024 * 1024 // CHUNK
    out = sys.stdout

    def emit(rec):
        out.write(json.dumps(rec, separators=(",", ":")) + "\n")
        out.flush()

    t_start = time.perf_counter_ns()
    deadline = t_start + int(a.max_seconds * 1e9)
    if not a.progress:
        emit({"p": a.proc, "ev": "start", "pid": os.getpid(), "cgroup": cg, "cur": current(),
              "unix": time.time(), "mono": t_start})
    else:
        print(f"pid {os.getpid()} in {cg}, memory.high={open(cg + '/memory.high').read().strip()}"
              f" memory.max={open(cg + '/memory.max').read().strip()}", flush=True)

    i = churn = 0
    reason = None
    next_print = t_start
    win_max = 0.0
    while True:
        ta = time.perf_counter_ns()
        if ta >= deadline:
            reason = "time"
            break
        phase = "g" if len(held) < target else "c"
        if phase == "c" and churn >= a.churn_ops:
            reason = "done"
            break
        cur = current()
        h0, m0 = high_max()
        t0 = time.perf_counter_ns()
        if a.kind == "anon":
            if phase == "c":
                j = int(rnd() * len(held))
                old = held[j]
                held[j] = held[-1]
                held.pop()
                old.close()
            m = mmap.mmap(-1, CHUNK, flags=flags, prot=mmap.PROT_READ | mmap.PROT_WRITE)
            m.write(payload)
            held.append(m)
            with memoryview(held[int(rnd() * len(held))]) as v:
                smv[:] = v
        else:
            if phase == "g":
                off = next_off
                next_off += CHUNK
                held.append(off)
            else:
                off = held[int(rnd() * len(held))]
            os.preadv(fd, [smv], off)
        t1 = time.perf_counter_ns()
        h1, m1 = high_max()
        cur_after = current()
        if a.progress:
            win_max = max(win_max, (t1 - t0) / 1e6)
            if t1 >= next_print:
                print(f"{(t1 - t_start) / 1e9:6.1f}s  held {len(held) * CHUNK >> 20:4d} MiB"
                      f"  memory.current {cur_after / 1048576:6.1f} MiB  ops {i + 1:5d}"
                      f"  slowest op {win_max:8.2f} ms", flush=True)
                next_print = t1 + 1_000_000_000
                win_max = 0.0
        else:
            emit({"p": a.proc, "i": i, "ph": phase, "t": ta - t_start, "op": t1 - t0,
                  "cur": cur, "cur2": cur_after, "dh": h1 - h0, "dm": m1 - m0,
                  "cpu": getcpu(),
                  "held": len(held) * CHUNK})
        i += 1
        if phase == "c":
            churn += 1

    end = {"p": a.proc, "ev": "end", "reason": reason, "ops": i, "held": len(held) * CHUNK,
           "cur": current(), "elapsed": time.perf_counter_ns() - t_start}
    if a.progress:
        print(f"end: {reason} after {end['elapsed'] / 1e9:.1f}s, {i} ops, held {end['held'] >> 20} MiB,"
              f" memory.current {end['cur'] / 1048576:.1f} MiB", flush=True)
    else:
        emit(end)


if __name__ == "__main__":
    main()
