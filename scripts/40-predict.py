#!/usr/bin/env python3
"""Compare the recorded runs with the over-high penalty in mm/memcontrol.c (Ubuntu 6.8.0-147).

Port of calculate_overage() + calculate_high_delay() + the clamp in
mem_cgroup_handle_over_high(), HZ=1000 (results/00-host.txt), nr_pages=64:

  overage = ((usage - high) << 20) / high          (pages)
  penalty = (overage^2 * HZ) >> 20 >> 14            (jiffies = ms)
  penalty = penalty * nr_pages / 64, at most 2 * HZ; no sleep if penalty <= HZ / 100

Checks:
  1. per-sleep time: measured op latency / (sleeps x penalty), where sleeps = the
     op's rise in memory.events "high" / 17
  2. the 2 s cap: per-sleep time in anon-clamp-high (usage 30% over high)
  3. time to the OOM kill in anon-over-both-long, predicted page by page with one
     sleep per 64 pages (the design) and one sleep per page (what we saw)
  4. PSI: memory.pressure "some" total vs the time the ops spent over baseline
  5. 1 process vs 4 processes under memory.high

Reads results/summary.json (run 30-summarize.py first) and the run directories.
Output: results/predict.json and results/predict.md
"""
import glob
import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HZ = 1000
HIGH = 241590272
MAX = 268435456
PAGE = 4096
BATCH = 64
CLAMP = 2 * HZ
BUCKETS = [(11, 25), (25, 50), (50, 100), (100, 200), (200, 400), (400, 2001)]


def penalty_ms(usage_bytes, high_bytes=HIGH, nr_pages=BATCH):
    usage, high = usage_bytes // PAGE, max(high_bytes // PAGE, 1)
    if usage <= high:
        return 0
    over = ((usage - high) << 20) // high
    p = (over * over * HZ) >> 20 >> 14
    p = p * nr_pages // BATCH
    p = min(p, CLAMP)
    return 0 if p <= HZ // 100 else p


def timer_step_ms(ms):
    """Granularity of the timer wheel level a timeout of ms lands in (HZ=1000, kernel/time/timer.c)."""
    for limit, step in ((64, 1), (512, 8), (4096, 64), (32768, 512)):
        if ms < limit:
            return step
    return 4096


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def ops_of(run_dir):
    recs = [json.loads(line) for line in open(os.path.join(run_dir, "ops.jsonl")) if line.strip()]
    return [r for r in recs if "i" in r], recs


def main():
    summ = json.load(open(os.path.join(ROOT, "results/summary.json")))
    runs = {(r["batch"], r["run"]): r for r in summ["runs"]}
    base = st.median(r["lat_ms"]["p50"] for r in summ["runs"] if r["config"] == "anon-fit-none")
    out = {"baseline_op_ms": base, "per_sleep": {}, "clamp": {}, "long": {}, "psi": {}, "procs": {},
           "sleeps_by_penalty": {}}
    by_pen = {}

    # 1. per-sleep time against the formula
    for (batch, run), r in sorted(runs.items()):
        # memory.events is per cgroup, so only one-process runs can be split per op
        if (r["kind"] != "anon" or r["limits"] not in ("high", "both") or r["code"] != "warm"
                or r["procs"] != 1 or r["config"] == "anon-clamp-high"):
            continue
        ops, _ = ops_of(os.path.join(ROOT, "results", batch, run))
        ratios, mixed, nosleep = [], 0, 0
        stepped = {"under_64ms": [], "64ms_or_more": []}
        for o in ops:
            if o.get("dh", 0) == 0:
                continue
            if o["dh"] % 17:
                mixed += 1
                continue
            sleeps = o["dh"] // 17
            pen = penalty_ms((o["cur"] + o["cur2"]) // 2)
            pred = sleeps * pen
            if pred == 0:
                nosleep += 1
                continue
            ratios.append((o["op"] / 1e6 - base) / pred)
            # the timer fires at the next step of its wheel level: on average half a step late
            k = "under_64ms" if pen < 64 else "64ms_or_more"
            stepped[k].append((o["op"] / 1e6 - base) / (sleeps * (pen + timer_step_ms(pen) / 2)))
            group = "matrix" if batch == "runs" else r["config"]
            for lo, hi in BUCKETS:
                if lo <= pen < hi and "--populate" not in (r["extra"] or []):
                    by_pen.setdefault(group, {}).setdefault(f"{lo}-{hi} ms", []).append(sleeps)
        out["per_sleep"][run] = {
            "ops_checked": len(ratios), "ops_with_partial_reclaim_rounds": mixed,
            "ops_predicted_no_sleep": nosleep,
            "ratio_p10": pct(ratios, 0.1), "ratio_p50": pct(ratios, 0.5), "ratio_p90": pct(ratios, 0.9),
            "within_30pct": (sum(1 for x in ratios if 0.7 <= x <= 1.3) / len(ratios)) if ratios else None,
            "ratio_p50_with_half_timer_step": {k: pct(v, 0.5) for k, v in stepped.items()},
        }

    for g, buckets in by_pen.items():
        out["sleeps_by_penalty"][g] = {
            k: {"ops": len(v), "sleeps_p10": pct(v, 0.1), "sleeps_p50": pct(v, 0.5),
                "share_64_or_more": round(sum(1 for x in v if x >= 64) / len(v), 3)}
            for k, v in buckets.items()}

    # 2. the 2 s cap
    for (batch, run), r in sorted(runs.items()):
        if r["config"] != "anon-clamp-high":
            continue
        ops, recs = ops_of(os.path.join(ROOT, "results", batch, run))
        sh = next((x for x in recs if x.get("ev") == "set_high"), None)
        churn = [o for o in ops if o["ph"] == "c" and o.get("dh", 0) > 0 and o["dh"] % 17 == 0]
        per_sleep = [o["op"] / 1e6 / (o["dh"] // 17) for o in churn]
        out["clamp"][run] = {
            "set_high_at_mib": round(sh["cur"] / 1048576, 1) if sh else None,
            "overage_pct": round(100 * (sh["cur"] - HIGH) / HIGH, 1) if sh else None,
            "formula_ms_unclamped": None if not sh else
            ((((sh["cur"] // PAGE - HIGH // PAGE) << 20) // (HIGH // PAGE)) ** 2 * HZ) >> 34,
            "churn_ops_with_sleeps": len(churn),
            "sleeps_per_op": sorted({o["dh"] // 17 for o in churn}),
            "per_sleep_ms_p50": pct(per_sleep, 0.5), "per_sleep_ms_min": min(per_sleep, default=None),
            "per_sleep_ms_max": max(per_sleep, default=None),
            "op_ms_max": max((o["op"] / 1e6 for o in churn), default=None),
        }

    # 3. time to the OOM kill with memory.high at 90% of memory.max
    for (batch, run), r in sorted(runs.items()):
        if r["config"] != "anon-over-both-long":
            continue
        ops, _ = ops_of(os.path.join(ROOT, "results", batch, run))
        first = next((o for o in ops if penalty_ms(o["cur"]) > 0), None)
        if not first:
            continue
        t0 = first["t"] / 1e9
        u0 = first["cur"]

        def walk(pages_per_sleep):
            t, u = 0.0, u0
            while u < MAX:
                t += penalty_ms(u) / 1e3
                u += pages_per_sleep * PAGE
            return t
        out["long"][run] = {
            "throttle_starts_at_s": round(t0, 1), "throttle_starts_at_mib": round(u0 / 1048576, 2),
            "measured_kill_after_s": r["kill_after_s"], "outcome": r["outcome"],
            "measured_from_throttle_start_s": round(r["kill_after_s"] - t0, 1) if r["kill_after_s"] else None,
            "predicted_one_sleep_per_64_pages_s": round(walk(64), 1),
            "predicted_one_sleep_per_page_s": round(walk(1), 1),
            "current_last_mib": r["current_last_mib"], "wall_s": r["wall_s"],
        }

    # 4. PSI vs time over baseline
    for (batch, run), r in sorted(runs.items()):
        if r["kind"] != "anon" or r["code"] != "warm" or r["limits"] == "none" or r["procs"] != 1:
            continue
        ops, _ = ops_of(os.path.join(ROOT, "results", batch, run))
        extra = sum(max(0.0, o["op"] / 1e6 - base) for o in ops) / 1e3
        out["psi"][run] = {"psi_mem_some_s": r["psi_mem_some_s"], "psi_mem_full_s": r["psi_mem_full_s"],
                           "op_time_over_baseline_s": round(extra, 2),
                           "ratio": round(r["psi_mem_some_s"] / extra, 3) if extra > 1 else None}

    # 5. one process vs four: growth in the last 60 s vs "each process sleeps once per 4 KiB page"
    for c in ("anon-over-high", "anon-over-both", "anon-over-4p-high"):
        rs = [r for r in summ["runs"] if r["config"] == c]
        pred = []
        for r in rs:
            pen = penalty_ms(int(r["current_last_mib"] * 1048576))
            pred.append(round(r["procs"] * 4 / (pen / 1e3), 1) if pen else None)
        out["procs"][c] = {"procs": rs[0]["procs"] if rs else None,
                           "current_last_mib": [r["current_last_mib"] for r in rs],
                           "mib_over_high": [round(r["current_last_mib"] - HIGH / 1048576, 1) for r in rs],
                           "growth_last_60s_kib_s": [r["growth_last_60s_kib_s"] for r in rs],
                           "predicted_one_sleep_per_page_kib_s": pred}

    with open(os.path.join(ROOT, "results/predict.json"), "w") as f:
        json.dump(out, f, indent=1)

    L = ["# Kernel formula vs measured", "",
         f"Baseline op latency (median p50 of `anon-fit-none`): {base:.3f} ms. Formula: see the header of "
         "`scripts/40-predict.py`.", "",
         "## 1. Time per sleep: measured / (sleeps x formula)", "",
         "| run | ops checked | p10 | p50 | p90 | within 30% | ops with partial rounds |", "| --- " * 7 + "|"]
    for run, v in out["per_sleep"].items():
        if v["ops_checked"]:
            L.append(f"| {run} | {v['ops_checked']} | {v['ratio_p10']:.3f} | {v['ratio_p50']:.3f} | "
                     f"{v['ratio_p90']:.3f} | {100 * v['within_30pct']:.0f}% | {v['ops_with_partial_reclaim_rounds']} |")
    L += ["", "Same ratio with half a timer-wheel step added to each sleep (1 ms step under 64 ms, 8 ms from 64 to 511 ms):", "",
          "| run | under 64 ms | 64 ms or more |", "| --- | --- | --- |"]
    for run, v in out["per_sleep"].items():
        h = v.get("ratio_p50_with_half_timer_step") or {}
        if v["ops_checked"]:
            f = lambda x: f"{x:.3f}" if x is not None else "-"
            L.append(f"| {run} | {f(h.get('under_64ms'))} | {f(h.get('64ms_or_more'))} |")
    L += ["", "## 1b. Sleeps per 256 KiB op (64 pages), by the formula's sleep length", "",
          "One-process warm runs that touch memory with page faults (not `--populate`), ops whose rise in `high` "
          "is a multiple of 17. 64 or more means one sleep per page. `matrix`: all such runs in results/runs, where "
          "the workload inherited the driver's CPU 0 and the driver sampled every 100 ms. `diag-*`: results/diag.", "",
          "| group | sleep length | ops | sleeps p10 | sleeps p50 | ops with 64 or more |", "| --- " * 6 + "|"]
    for g, buckets in out["sleeps_by_penalty"].items():
        for lo, hi in BUCKETS:
            v = buckets.get(f"{lo}-{hi} ms")
            if v:
                L.append(f"| {g} | {lo} to {hi} ms | {v['ops']} | {v['sleeps_p10']} | {v['sleeps_p50']} | {100 * v['share_64_or_more']:.0f}% |")
    L += ["", "## 2. The 2 s cap (`MEMCG_MAX_HIGH_DELAY_JIFFIES`)", "",
          "| run | memory.high set at MiB | over high | formula without cap, ms | ops | sleeps per op | per sleep p50 ms | min | max |",
          "| --- " * 9 + "|"]
    for run, v in out["clamp"].items():
        L.append(f"| {run} | {v['set_high_at_mib']} | {v['overage_pct']}% | {v['formula_ms_unclamped']} | "
                 f"{v['churn_ops_with_sleeps']} | {v['sleeps_per_op']} | {v['per_sleep_ms_p50']:.1f} | "
                 f"{v['per_sleep_ms_min']:.1f} | {v['per_sleep_ms_max']:.1f} |" if v["per_sleep_ms_p50"] else f"| {run} | no data |")
    L += ["", "## 3. Time to the OOM kill, memory.high = 90% of memory.max", ""]
    for run, v in out["long"].items():
        L.append(f"- {run}: throttling starts at {v['throttle_starts_at_s']} s ({v['throttle_starts_at_mib']} MiB). "
                 f"Outcome {v['outcome']}, killed after {v['measured_kill_after_s']} s "
                 f"({v['measured_from_throttle_start_s']} s after throttling started). Predicted from that point: "
                 f"{v['predicted_one_sleep_per_64_pages_s']} s with one sleep per 64 pages, "
                 f"{v['predicted_one_sleep_per_page_s']} s with one sleep per page.")
    L += ["", "## 4. PSI memory `some` total vs op time over baseline", "",
          "| run | PSI some s | PSI full s | op time over baseline s | ratio |", "| --- " * 5 + "|"]
    for run, v in out["psi"].items():
        L.append(f"| {run} | {v['psi_mem_some_s']} | {v['psi_mem_full_s']} | {v['op_time_over_baseline_s']} | {v['ratio']} |")
    L += ["", "## 5. Growth at the time cap: measured vs one sleep per 4 KiB page per process", "",
          "Predicted growth = processes x 4 KiB / formula sleep at the last memory.current. Per repetition.", "",
          "| config | processes | last memory.current MiB | measured KiB/s | predicted KiB/s |", "| --- " * 5 + "|"]
    for c, v in out["procs"].items():
        L.append(f"| {c} | {v['procs']} | {v['current_last_mib']} | {v['growth_last_60s_kib_s']} | "
                 f"{v['predicted_one_sleep_per_page_kib_s']} |")
    with open(os.path.join(ROOT, "results/predict.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
