#!/usr/bin/env python3
"""Summarize every run in results/<batch>/ into results/summary.json and results/summary.md.

Refuses to run when a run directory is incomplete, when the runs in one batch carry
different code stamps, or when a stamp matches no commit of the run code in this
repository's history. Directories that start with "_" (smoke runs) are skipped.

usage: scripts/30-summarize.py [--partial]
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import statistics as st
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_FILES = ["scripts/lib/workload.py", "scripts/lib/matrix.py", "scripts/20-run-matrix.sh"]
BATCHES = ["runs", "clamp", "diag"]
MIB = 1048576
HIGH = 241590272
MAX = 268435456
EVENTS_PER_SLEEP = 17  # reclaim_high() runs 1 + MAX_RECLAIM_RETRIES (16) times before a sleep


def stamps_by_commit():
    """code stamp -> commit, for every commit that touched the run code."""
    out = {}
    commits = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "--", *CODE_FILES],
                             capture_output=True, text=True, check=True).stdout.split()
    for c in commits:
        h = hashlib.sha256()
        try:
            for f in CODE_FILES:
                blob = subprocess.run(["git", "-C", ROOT, "show", f"{c}:{f}"], capture_output=True,
                                      check=True).stdout
                h.update(f.encode() + b"\0" + blob)
        except subprocess.CalledProcessError:
            continue
        out[h.hexdigest()[:16]] = c[:12]
    return out


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def kill_time(final, start_unix):
    for line in final.get("kernel_log", []):
        if "Killed process" in line:
            ts = line.split()[0]
            t = datetime.datetime.fromisoformat(ts).timestamp()
            return t - start_unix
    return None


def summarize_run(d):
    meta = json.load(open(os.path.join(d, "meta.json")))
    final = json.load(open(os.path.join(d, "final.json")))
    recs = [json.loads(line) for line in open(os.path.join(d, "ops.jsonl")) if line.strip()]
    samples = [json.loads(line) for line in open(os.path.join(d, "samples.jsonl")) if line.strip()]
    ops = [r for r in recs if "i" in r]
    starts = [r for r in recs if r.get("ev") == "start"]
    ends = [r for r in recs if r.get("ev") == "end"]
    start_unix = min(r["unix"] for r in starts) if starts else None
    ev = final["events"]
    if ev.get("oom_kill", 0) > 0:
        outcome = "oom_kill"
    elif ends and len(ends) == meta["procs"] and all(e["reason"] == "done" for e in ends):
        outcome = "done"
    else:
        outcome = "cap"  # still running at the time cap: not finished, not killed by the kernel
    lat = [r["op"] / 1e6 for r in ops]
    thr = [r for r in ops if r.get("dh", 0) > 0]
    # the workload clock starts a few ms after the sampler clock; cut samples at the last op
    # so that a process that is exiting (and freeing memory) does not count
    # with several processes, cut at the first one to stop
    ends_by_proc = {}
    for r in ops:
        ends_by_proc[r["p"]] = max(ends_by_proc.get(r["p"], 0), (r["t"] + r["op"]) / 1e9)
    t_last = min(ends_by_proc.values(), default=0) + 0.1
    alive = [s for s in samples if s.get("nprocs", 0) > 0 and "current" in s and s["t"] / 1e9 <= t_last]
    last = alive[-1] if alive else (samples[-1] if samples else {})
    cur_series = [(s["t"] / 1e9, s["current"]) for s in alive]
    slope = None
    if cur_series and cur_series[-1][0] > 70:
        t_end = cur_series[-1][0]
        win = [(t, c) for t, c in cur_series if t >= t_end - 60]
        if len(win) > 10:
            slope = (win[-1][1] - win[0][1]) / 1024 / (win[-1][0] - win[0][0])  # KiB/s
    procs = {}
    for s in samples:
        for pid, p in s.get("proc", {}).items():
            procs[pid] = p
    io = final.get("io", {})
    rbytes = sum(v.get("rbytes", 0) for v in io.values())
    last_tenth = lat[int(0.9 * len(lat)):] if lat else []
    out = {
        "run": os.path.basename(d), "batch": os.path.basename(os.path.dirname(d)),
        "config": meta["name"].rsplit("-r", 1)[0], "rep": meta["rep"], "kind": meta["kind"],
        "limits": meta["limits"], "code": meta.get("code"), "procs": meta["procs"],
        "io_cap": meta.get("io_cap"), "extra": meta.get("extra_args"), "stamp": meta["stamp"],
        "utc_start": meta["utc_start"], "outcome": outcome, "hard_killed": final["hard_killed"],
        "wall_s": round(final["wall_ns"] / 1e9, 2),
        "kill_after_s": round(kill_time(final, start_unix), 2) if outcome == "oom_kill" and start_unix else None,
        "ops": len(ops),
        "held_end_mib": round(max((r["held"] for r in ops), default=0) / MIB, 1),
        "peak_mib": round(final["peak"] / MIB, 1),
        "current_last_mib": round(last.get("current", 0) / MIB, 1),
        "churn_ops": sum(1 for r in ops if r["ph"] == "c"),
        "churn_p50_ms": pct([r["op"] / 1e6 for r in ops if r["ph"] == "c"], 0.5),
        "lat_ms": {"p50": pct(lat, 0.5), "p99": pct(lat, 0.99), "max": max(lat) if lat else None,
                   "p99_last_tenth": pct(last_tenth, 0.99)},
        "sum_op_s": round(sum(lat) / 1e3, 2),
        # time from the end of the last completed op to the end of the run: an op that never
        # finished (stuck, then killed by the kernel or the driver) does not show in the percentiles
        "unfinished_op_s": round(max(0.0, final["wall_ns"] / 1e9 - max(((r["t"] + r["op"]) / 1e9 for r in ops), default=0)), 1),
        # memory.events is per cgroup: with several processes, one op's rise includes the others
        "ops_with_high_events": len(thr),
        "high_events_per_17": round(sum(r["dh"] for r in ops) / EVENTS_PER_SLEEP, 1),
        "events": ev,
        "psi_mem_some_s": round(final["pressure"]["some"]["total"] / 1e6, 2),
        "psi_mem_full_s": round(final["pressure"]["full"]["total"] / 1e6, 2),
        "psi_mem_some_avg10_max": max((s.get("pressure", {}).get("some", {}).get("avg10", 0) for s in samples), default=0),
        "psi_io_some_s": round(final.get("io_pressure", {}).get("some", {}).get("total", 0) / 1e6, 2),
        "cpu_s": {k: round(final.get("cpu", {}).get(k, 0) / 1e6, 2) for k in ("usage_usec", "user_usec", "system_usec")},
        "stat_last": {k: last.get("stat", {}).get(k) for k in ("anon", "file", "shmem", "kernel")},
        "pgsteal": final["stat"].get("pgsteal"),
        "refault_file": final["stat"].get("workingset_refault_file"),
        "majflt": sum(p.get("majflt", 0) for p in procs.values()),
        "disk_read_mb": round(rbytes / 1e6, 1),
        "growth_last_60s_kib_s": round(slope, 2) if slope is not None else None,
        "wchan_top": Counter(v for s in samples for v in s.get("wchan", {}).values() if v).most_common(3),
        "end_reasons": [e["reason"] for e in ends],
        "high_end": final.get("readback_end", {}).get("memory.high", meta["readback"]["memory.high"]),
    }
    return out


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partial", action="store_true", help="skip incomplete runs (for a look while running)")
    a = ap.parse_args()
    known = stamps_by_commit()
    runs = []
    for b in BATCHES:
        dirs = sorted(glob.glob(os.path.join(ROOT, "results", b, "*")))
        dirs = [d for d in dirs if os.path.isdir(d)]
        if not dirs:
            continue
        batch_stamps = set()
        for d in dirs:
            if not os.path.exists(os.path.join(d, "final.json")):
                if a.partial:
                    continue
                sys.exit(f"incomplete run {d}; refusing (use --partial to look anyway)")
            r = summarize_run(d)
            batch_stamps.add(r["stamp"])
            runs.append(r)
        if len(batch_stamps) > 1:
            sys.exit(f"batch {b} mixes code stamps {sorted(batch_stamps)}; refusing")
        for s in batch_stamps:
            if s not in known:
                sys.exit(f"batch {b} stamp {s} matches no commit of the run code; refusing")
    configs = {}
    for r in runs:
        configs.setdefault((r["batch"], r["config"]), []).append(r)
    agg = []
    for (b, c), rs in configs.items():
        agg.append({
            "batch": b, "config": c, "reps": len(rs), "commit": known[rs[0]["stamp"]],
            "outcomes": [r["outcome"] for r in rs],
            "kill_after_s": [r["kill_after_s"] for r in rs],
            "wall_s": med([r["wall_s"] for r in rs]),
            "ops": med([r["ops"] for r in rs]),
            "churn_ops": med([r["churn_ops"] for r in rs]),
            "churn_p50_ms": med([r["churn_p50_ms"] for r in rs]),
            "held_end_mib": med([r["held_end_mib"] for r in rs]),
            "peak_mib": med([r["peak_mib"] for r in rs]),
            "current_last_mib": med([r["current_last_mib"] for r in rs]),
            "lat_p50_ms": med([r["lat_ms"]["p50"] for r in rs]),
            "lat_p99_ms": med([r["lat_ms"]["p99"] for r in rs]),
            "lat_max_ms": med([r["lat_ms"]["max"] for r in rs]),
            "lat_p99_last_tenth_ms": med([r["lat_ms"]["p99_last_tenth"] for r in rs]),
            "unfinished_op_s": med([r["unfinished_op_s"] for r in rs]),
            "events_high": med([r["events"].get("high", 0) for r in rs]),
            "events_max": med([r["events"].get("max", 0) for r in rs]),
            "oom_kills": sum(r["events"].get("oom_kill", 0) for r in rs),
            "psi_mem_some_s": med([r["psi_mem_some_s"] for r in rs]),
            "psi_mem_full_s": med([r["psi_mem_full_s"] for r in rs]),
            "psi_mem_some_share": med([r["psi_mem_some_s"] / r["wall_s"] for r in rs if r["wall_s"]]),
            "psi_io_some_s": med([r["psi_io_some_s"] for r in rs]),
            "cpu_s": med([r["cpu_s"]["usage_usec"] for r in rs]),
            "pgsteal": med([r["pgsteal"] for r in rs]),
            "refault_file": med([r["refault_file"] for r in rs]),
            "disk_read_mb": med([r["disk_read_mb"] for r in rs]),
            "growth_last_60s_kib_s": med([r["growth_last_60s_kib_s"] for r in rs]),
        })
    out = {"generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "commits": {s: known[s] for s in {r["stamp"] for r in runs}}, "configs": agg, "runs": runs}
    with open(os.path.join(ROOT, "results/summary.json"), "w") as f:
        json.dump(out, f, indent=1)

    def fmt(v, nd=1):
        if v is None:
            return "-"
        if isinstance(v, float):
            return f"{v:,.{nd}f}"
        return f"{v:,}" if isinstance(v, int) else str(v)

    lines = ["# Summary", "", f"Generated by `scripts/30-summarize.py` from `results/{{{','.join(BATCHES)}}}/`. "
             "Medians over repetitions. Latency is per 256 KiB op (4 KiB in `anon-clamp-high` churn). "
             "Last memory.current: the last sample before the first process stopped (for an OOM kill, "
             "use the peak: the workload grows 256 MiB in under a second, faster than the 100 ms sampler).", "",
             "| config | reps | outcomes | kill after s | ops | churn ops | churn p50 ms | peak MiB | last memory.current MiB | p50 ms | p99 ms "
             "| max ms | unfinished op s | high events | max events | PSI mem some s (share) | PSI io some s "
             "| CPU s | pgsteal | disk read MB | growth KiB/s (last 60 s) |",
             "| --- " * 21 + "|"]
    for g in agg:
        oc = Counter(g["outcomes"])
        lines.append("| " + " | ".join([
            g["config"], str(g["reps"]), ", ".join(f"{k} x{v}" for k, v in oc.items()),
            ", ".join(fmt(x) for x in g["kill_after_s"] if x is not None) or "-",
            fmt(g["ops"], 0), fmt(g["churn_ops"], 0), fmt(g["churn_p50_ms"], 3), fmt(g["peak_mib"]), fmt(g["current_last_mib"]), fmt(g["lat_p50_ms"], 3),
            fmt(g["lat_p99_ms"], 2), fmt(g["lat_max_ms"], 1), fmt(g["unfinished_op_s"]), fmt(g["events_high"], 0),
            fmt(g["events_max"], 0),
            f"{fmt(g['psi_mem_some_s'])} ({fmt(100 * g['psi_mem_some_share'] if g['psi_mem_some_share'] is not None else None, 0)}%)",
            fmt(g["psi_io_some_s"]), fmt(g["cpu_s"], 2), fmt(g["pgsteal"], 0), fmt(g["disk_read_mb"], 0),
            fmt(g["growth_last_60s_kib_s"]),
        ]) + " |")
    lines += ["", "Per run: `results/summary.json` (`runs`). Code commits per stamp: " +
              ", ".join(f"`{s}` = {c}" for s, c in out["commits"].items()) + "."]
    with open(os.path.join(ROOT, "results/summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
