#!/usr/bin/env python3
"""Build the chart specs for the post from the recorded runs. Output: results/charts.json

1. latency: median op latency per 1 MiB of memory.current (all repetitions), for the
   anon-over runs (warm code), with the formula at one sleep per 64 pages and one
   sleep per page
2. growth: memory.current over the first 150 s, anon-over high (1 and 4 processes)
   and both, median of the repetitions at each 10 s mark
3. long: memory.current over time in anon-over-both-long, one point a minute
"""
import glob
import importlib.util
import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIB = 1048576
spec = importlib.util.spec_from_file_location("predict", os.path.join(ROOT, "scripts/40-predict.py"))
predict = importlib.util.module_from_spec(spec)
spec.loader.exec_module(predict)


def runs_of(batch, config):
    return sorted(d for d in glob.glob(os.path.join(ROOT, "results", batch, config + "-r*"))
                  if os.path.exists(os.path.join(d, "final.json")))


def ops(d):
    return [json.loads(line) for line in open(os.path.join(d, "ops.jsonl")) if '"i"' in line]


def samples(d):
    return [json.loads(line) for line in open(os.path.join(d, "samples.jsonl")) if line.strip()]


def by_mib(config, lo, hi):
    b = {}
    for d in runs_of("runs", config):
        for o in ops(d):
            k = int(o["cur"] / MIB)
            if lo <= k <= hi:
                b.setdefault(k, []).append(o["op"] / 1e6)
    xs = list(range(lo, hi + 1))
    data = []
    for k in xs:
        if k not in b:
            break
        data.append(round(st.median(b[k]), 3))
    return data


def main():
    lo, hi = 226, 244  # the memory.high runs end at about 242 MiB; past that only the formula has values
    x = list(range(lo, hi + 1))
    base = st.median(o["op"] / 1e6 for d in runs_of("runs", "anon-over-none") for o in ops(d))
    f64 = [round(base + predict.penalty_ms(m * MIB + MIB // 2), 3) for m in x]
    f1 = [round(base + 64 * predict.penalty_ms(m * MIB + MIB // 2), 3) for m in x]
    latency = {
        "type": "line", "log": True, "unit": "ms",
        "title": "Latency of one 256 KiB allocation vs memory.current",
        "x": [f"{m}" for m in x],
        "series": [
            {"name": "no limit", "data": by_mib("anon-over-none", lo, hi), "color": "#94a3b8"},
            {"name": "memory.max only", "data": by_mib("anon-over-max", lo, hi), "color": "#0080ff"},
            {"name": "memory.high only", "data": by_mib("anon-over-high", lo, hi), "color": "#f59e0b"},
            {"name": "kernel formula, 1 sleep per 64 pages", "data": f64, "dash": "6 5", "color": "#10b981"},
            {"name": "kernel formula, 1 sleep per page", "data": f1, "dash": "2 4", "color": "#ef4444"},
        ],
        "refs": [{"value": 1, "label": "1 ms"}],
        "caption": "x axis: memory.current in MiB when the op started (memory.high = 230.4 MiB, memory.max = 256 MiB). "
                   "Median per 1 MiB over 3 repetitions of anon-over, warm code, Ubuntu 6.8.0-147, no swap. "
                   "memory.max only stays flat up to 256 MiB, then the OOM kill. The formula lines add the "
                   "no-limit median to the kernel's sleep: once per 64-page op, or once per 4 KiB page. "
                   "Source: results/runs/anon-over-*/ops.jsonl, scripts/50-charts.py.",
    }

    def growth(config, step=10, until=150):
        ds = runs_of("runs", config)
        series = []
        for t in range(step, until + 1, step):
            vals = []
            for d in ds:
                ss = [s for s in samples(d) if "current" in s and s.get("nprocs", 0) > 0]
                near = [s for s in ss if abs(s["t"] / 1e9 - t) <= 0.15]
                if near:
                    vals.append(near[0]["current"] / MIB)
            if not vals:
                break
            series.append(round(st.median(vals), 1))
        return series

    grow = {
        "type": "line", "unit": " MiB",
        "title": "memory.current from 10 s to 150 s, the workload asks for 320 MiB",
        "x": [f"{t}s" for t in range(10, 151, 10)],
        "series": [
            {"name": "memory.high only, 1 process", "data": growth("anon-over-high"), "color": "#f59e0b"},
            {"name": "memory.high only, 4 processes", "data": growth("anon-over-4p-high"), "color": "#a855f7"},
            {"name": "memory.high + memory.max", "data": growth("anon-over-both"), "color": "#0080ff"},
        ],
        "refs": [{"value": 230.4, "label": "memory.high"}, {"value": 256, "label": "memory.max", "color": "#ef4444"}],
        "caption": "Median of 3 repetitions at each 10 s mark, sampled from outside the cgroup every 100 ms. "
                   "memory.max only reaches 256 MiB and is killed in under 2 s, so it is not drawn. "
                   "Source: results/runs/anon-over-*/samples.jsonl.",
    }
    out = {"latency": latency, "growth": grow}

    longs = runs_of("runs", "anon-over-both-long")
    if longs:
        ss = [s for s in samples(longs[0]) if "current" in s and s.get("nprocs", 0) > 0]
        end = ss[-1]["t"] / 1e9
        pts, xs = [], []
        for m in range(0, int(end // 60) + 1):
            near = [s for s in ss if abs(s["t"] / 1e9 - 60 * m) <= 0.15]
            if near:
                xs.append(f"{m}m")
                pts.append(round(near[0]["current"] / MIB, 1))
        out["long"] = {
            "type": "line", "unit": " MiB",
            "title": "memory.high at 90% of memory.max: the climb to the OOM kill",
            "x": xs, "series": [{"name": "memory.current", "data": pts, "color": "#f59e0b"}],
            "refs": [{"value": 230.4, "label": "memory.high"}, {"value": 256, "label": "memory.max", "color": "#ef4444"}],
            "caption": "One run, sampled every 100 ms, one point a minute. Source: results/runs/anon-over-both-long-r1/samples.jsonl.",
        }
    with open(os.path.join(ROOT, "results/charts.json"), "w") as f:
        json.dump(out, f, indent=1)
    for k, v in out.items():
        print(k, json.dumps(v)[:300])


if __name__ == "__main__":
    main()
