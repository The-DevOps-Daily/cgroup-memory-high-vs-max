#!/usr/bin/env python3
"""Run the measurement matrix inside a delegated cgroup subtree.

Start it with scripts/20-run-matrix.sh. That puts this process in a transient
systemd scope with Delegate=yes and MemoryMax=1G. This script then moves
itself to <scope>/driver, turns on the memory controller for the children,
and for each run:

  1. makes <scope>/<run>, writes memory.high and memory.max, reads them back
  2. starts the workload in that cgroup (a shell writes its PID to
     cgroup.procs, then execs python, so the interpreter is charged there too)
  3. samples memory.current, memory.events, memory.pressure, memory.stat and
     the workload's /proc/<pid>/wchan every 100 ms from outside the cgroup
  4. after the workload exits, reads the final files and the kernel log lines
     for that cgroup, then removes the cgroup

Every file it writes carries the same code stamp (sha256 of the run code).
"""
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CODE_FILES = ["scripts/lib/workload.py", "scripts/lib/matrix.py", "scripts/20-run-matrix.sh"]
WORKLOAD = os.path.join(ROOT, "scripts/lib/workload.py")
DATA_FILE = os.path.join(ROOT, "work/data.bin")

MIB = 1024 * 1024
MAX = 268435456  # 256 MiB
HIGH = 241590272  # floor(0.9 * 256 MiB / 4096) * 4096, what kubelet MemoryQoS writes for 256Mi
CAP = 1024 * MIB  # no limit in this repo goes above 1 GiB
IO_BPS = 100 * MIB  # io.max read and write cap per run, so thrashing runs share the disk
W1 = 232  # anon-fit target in MiB: results/_smoke1/anon-fit-none-r1 peaked at 238.8 MiB

LIMITS = {"none": (None, None), "max": (None, MAX), "high": (HIGH, None), "both": (HIGH, MAX)}
# code "warm": before the run, the driver starts the same interpreter and imports, so
#   their page cache is charged outside the run cgroup. The run cgroup holds only
#   what the workload allocates.
# code "own": the run execs a fresh copy of the interpreter binary that is not in
#   the page cache, so its code pages are read and charged inside the run cgroup,
#   like a container on its first start. These runs re-read the binary from disk
#   while they thrash, so they are capped at 20 s.
# seconds: per-run cap (default --max-seconds). The driver kills a run 5 s after it.
# default False: runs only when named in --only.
# reps: run only in repetitions 1..reps.
# io False: no io.max cap on this run (the disk's own speed).


def cfg(name, kind, target, limits, procs=1, extra=(), code="warm", seconds=None, default=True,
        reps=99, io=True):
    return {"name": name, "kind": kind, "target": target, "limits": limits, "procs": procs,
            "extra": list(extra), "code": code, "seconds": seconds, "default": default,
            "reps": reps, "io": io}


CONFIGS = [
    cfg("anon-fit-none", "anon", W1, "none"),
    cfg("anon-fit-max", "anon", W1, "max"),
    cfg("anon-fit-high", "anon", W1, "high"),
    cfg("anon-fit-both", "anon", W1, "both"),
    cfg("anon-fit-high-populate", "anon", W1, "high", extra=["--populate"]),
    cfg("anon-fit-high-owncode", "anon", W1, "high", code="own", seconds=20),
    cfg("anon-over-none", "anon", 320, "none"),
    cfg("anon-over-max", "anon", 320, "max"),
    cfg("anon-over-high", "anon", 320, "high"),
    cfg("anon-over-both", "anon", 320, "both"),
    cfg("anon-over-4p-high", "anon", 320, "high", procs=4),
    cfg("anon-over-max-owncode", "anon", 320, "max", code="own", seconds=20),
    cfg("anon-over-both-owncode", "anon", 320, "both", code="own", seconds=20),
    cfg("anon-over-max-owncode-fastdisk", "anon", 320, "max", code="own", seconds=20, reps=1,
        io=False),
    cfg("file-over-none", "file", 320, "none"),
    cfg("file-over-max", "file", 320, "max"),
    cfg("file-over-high", "file", 320, "high"),
    cfg("file-over-both", "file", 320, "both"),
    cfg("anon-over-both-long", "anon", 320, "both", seconds=2700, default=False),
    # grow to 300 MiB with no limit, then set memory.high 30% below usage and allocate
    # one 4 KiB page per op: every sleep should hit the 2 s cap
    cfg("anon-clamp-high", "anon", 300, "none", seconds=40, default=False,
        extra=["--set-high-after-grow", str(HIGH), "--churn-kib", "4"]),
]
PYTHON = os.path.realpath("/usr/bin/python3")
STAT_KEYS = ["anon", "file", "shmem", "file_mapped", "active_file", "inactive_file", "kernel",
             "kernel_stack", "pagetables", "slab", "sock", "file_dirty", "file_writeback", "pgscan",
             "pgsteal", "pgscan_direct", "pgsteal_direct", "pgmajfault", "workingset_refault_anon",
             "workingset_refault_file", "pgfault"]


def code_stamp():
    h = hashlib.sha256()
    for f in CODE_FILES:
        with open(os.path.join(ROOT, f), "rb") as fh:
            h.update(f.encode() + b"\0" + fh.read())
    return h.hexdigest()[:16]


def read(path):
    with open(path) as f:
        return f.read()


def write(path, value):
    with open(path, "w") as f:
        f.write(value)


def kv(text):
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(" ")
        if v.strip().lstrip("-").isdigit():
            out[k] = int(v)
    return out


def pressure(text):
    out = {}
    for line in text.splitlines():
        parts = line.split()
        out[parts[0]] = {k: float(v) for k, v in (p.split("=") for p in parts[1:])}
    return out


def io_stat(text):
    out = {}
    for line in text.splitlines():
        dev, *fields = line.split()
        out[dev] = {k: int(v) for k, v in (f.split("=") for f in fields)}
    return out


def disk_of(path):
    """major:minor of the whole disk that holds path (io.max wants the disk, not a partition)."""
    src = subprocess.run(["findmnt", "-no", "SOURCE", "--target", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    pk = subprocess.run(["lsblk", "-no", "PKNAME", src], capture_output=True, text=True,
                        check=True).stdout.strip() or os.path.basename(src)
    return read(f"/sys/block/{pk}/dev").strip()


def mem_available():
    for line in read("/proc/meminfo").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return 0


def resident_pages(path):
    """Pages of a file that sit in the page cache, via mmap + mincore."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
    size = os.path.getsize(path)
    fd = os.open(path, os.O_RDONLY)
    try:
        addr = libc.mmap(None, size, 1, 1, fd, 0)  # PROT_READ, MAP_SHARED
        n = (size + 4095) // 4096
        vec = (ctypes.c_ubyte * n)()
        if libc.mincore(ctypes.c_void_p(addr), ctypes.c_size_t(size), vec) != 0:
            raise OSError(ctypes.get_errno(), "mincore")
        libc.munmap(ctypes.c_void_p(addr), ctypes.c_size_t(size))
        return sum(b & 1 for b in vec)
    finally:
        os.close(fd)


def drop_file_cache(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)


def sample(cg, pids, t0):
    rec = {"t": time.perf_counter_ns() - t0}
    try:
        rec["current"] = int(read(cg + "/memory.current"))
        rec["events"] = kv(read(cg + "/memory.events"))
        rec["pressure"] = pressure(read(cg + "/memory.pressure"))
        stat = kv(read(cg + "/memory.stat"))
        rec["stat"] = {k: stat.get(k) for k in STAT_KEYS}
        rec["nprocs"] = len(read(cg + "/cgroup.procs").split())
        rec["io"] = io_stat(read(cg + "/io.stat"))
        rec["io_pressure"] = pressure(read(cg + "/io.pressure"))
        rec["cpu"] = kv(read(cg + "/cpu.stat"))
    except OSError as e:
        rec["error"] = str(e)
    w, ps = {}, {}
    for p in pids:
        try:
            w[str(p)] = read(f"/proc/{p}/wchan")
            f = read(f"/proc/{p}/stat").rsplit(")", 1)[1].split()
            # fields after the name: state=0, minflt=7, majflt=9, utime=11, stime=12 (clock ticks)
            ps[str(p)] = {"state": f[0], "minflt": int(f[7]), "majflt": int(f[9]),
                          "utime": int(f[11]), "stime": int(f[12])}
        except (OSError, IndexError):
            w[str(p)] = None
    rec["wchan"] = w
    rec["proc"] = ps
    return rec


def kernel_log(since_unix, needle):
    try:
        out = subprocess.run(["journalctl", "-k", "--no-pager", "-o", "short-iso-precise",
                              "--since", "@%d" % int(since_unix)],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception as e:  # journal not readable: say so in the record
        return ["journalctl failed: %s" % e]
    keep = []
    for line in out.splitlines():
        if needle in line or "Memory cgroup out of memory" in line or "oom-kill:" in line:
            keep.append(line)
    return keep


def own_python(run):
    """Copy the interpreter to a new file and drop it from the page cache."""
    d = os.path.join(ROOT, "work", "own-" + run)
    os.makedirs(d)
    dst = os.path.join(d, "python3")
    with open(PYTHON, "rb") as src, open(dst, "wb") as out:
        out.write(src.read())
        out.flush()
        os.fsync(out.fileno())
    os.chmod(dst, 0o755)
    drop_file_cache(dst)
    return dst


def run_one(scope, name, c, rep, outdir, stamp, max_seconds, churn_ops):
    kind, target, nprocs, limits_key, extra, code = (c["kind"], c["target"], c["procs"],
                                                     c["limits"], c["extra"], c["code"])
    high, mx = LIMITS[limits_key]
    for v in (high, mx):
        if v is not None and v > CAP:
            sys.exit("refusing a limit above 1 GiB")
    waited = 0
    while mem_available() < 2048 * MIB:
        if waited > 300:
            sys.exit("host MemAvailable below 2 GiB for 5 minutes, stopping")
        time.sleep(10)
        waited += 10

    cg = os.path.join(scope, name)
    os.mkdir(cg)
    if high is not None:
        write(cg + "/memory.high", str(high))
    if mx is not None:
        write(cg + "/memory.max", str(mx))
    if c["io"]:
        write(cg + "/io.max", f"{disk_of(ROOT)} rbps={IO_BPS} wbps={IO_BPS}")
    meta = {
        "stamp": stamp, "name": name, "kind": kind, "target_mib": target, "procs": nprocs,
        "extra_args": extra, "code": code, "io_cap": c["io"],
        "limits": limits_key, "rep": rep, "max_seconds": max_seconds, "churn_ops": churn_ops,
        "cgroup": cg,
        "readback": {f: read(cg + "/" + f).strip() for f in
                     ["memory.high", "memory.max", "memory.low", "memory.min", "memory.swap.max",
                      "memory.oom.group", "io.max"]},
        "host": {"uname": " ".join(os.uname()), "mem_available": mem_available(),
                 "loadavg": read("/proc/loadavg").strip(),
                 "pressure_memory": pressure(read("/proc/pressure/memory"))},
        "scope_events_before": kv(read(scope + "/memory.events")),
        "utc_start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if kind == "file":
        drop_file_cache(DATA_FILE)
        meta["data_file_resident_pages_before"] = resident_pages(DATA_FILE)
    if code == "own":
        python = own_python(name)
        meta["python_copy_resident_pages_before"] = resident_pages(python)
    else:
        python = PYTHON
        subprocess.run([python, "-I", WORKLOAD, "--help"], check=True, capture_output=True)

    os.makedirs(outdir)
    ops_f = open(os.path.join(outdir, "ops.jsonl"), "w")
    smp_f = open(os.path.join(outdir, "samples.jsonl"), "w")
    unix0 = time.time()
    t0 = time.perf_counter_ns()
    procs = []
    per = target // nprocs
    for p in range(nprocs):
        argv = ["sh", "-c", 'echo $$ > "$1" && shift && exec "$@"', "sh", cg + "/cgroup.procs",
                python, "-I", WORKLOAD, "--kind", kind, "--target-mib", str(per),
                "--churn-ops", str(churn_ops // nprocs), "--max-seconds", str(max_seconds),
                "--seed", str(1000 * rep + p), "--cgroup", cg, "--proc", str(p)]
        if kind == "file":
            argv += ["--file", DATA_FILE]
        argv += extra
        procs.append(subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    meta["argv0"] = procs[0].args
    pipes = {pr.stdout.fileno(): pr for pr in procs}
    errs = {pr.pid: b"" for pr in procs}
    for fd in pipes:
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    bufs = {fd: b"" for fd in pipes}
    pids = [pr.pid for pr in procs]
    open_fds = set(pipes)
    hard_deadline = t0 + int((max_seconds + 5) * 1e9)
    hard_killed = False
    next_sample = t0
    while open_fds:
        now = time.perf_counter_ns()
        if now >= next_sample:
            smp_f.write(json.dumps(sample(cg, pids, t0), separators=(",", ":")) + "\n")
            next_sample = now + 100_000_000
        if now >= hard_deadline and not hard_killed:
            for pr in procs:
                pr.kill()
            hard_killed = True
        timeout = max(0.0, (next_sample - time.perf_counter_ns()) / 1e9)
        ready, _, _ = select.select(list(open_fds), [], [], timeout)
        for fd in ready:
            try:
                chunk = os.read(fd, 1 << 16)
            except BlockingIOError:
                continue
            if not chunk:
                open_fds.discard(fd)
                continue
            bufs[fd] += chunk
            *lines, bufs[fd] = bufs[fd].split(b"\n")
            for line in lines:
                ops_f.write(line.decode() + "\n")
    for pr in procs:
        pr.wait()
        errs[pr.pid] = pr.stderr.read()
    smp_f.write(json.dumps(sample(cg, [], t0), separators=(",", ":")) + "\n")
    ops_f.close()
    smp_f.close()

    final = {
        "stamp": stamp,
        "returncodes": [pr.returncode for pr in procs],
        "stderr": [errs[pr.pid].decode(errors="replace")[-2000:] for pr in procs],
        "hard_killed": hard_killed,
        "wall_ns": time.perf_counter_ns() - t0,
        "events": kv(read(cg + "/memory.events")),
        "events_local": kv(read(cg + "/memory.events.local")),
        "pressure": pressure(read(cg + "/memory.pressure")),
        "peak": int(read(cg + "/memory.peak")),
        "io": io_stat(read(cg + "/io.stat")),
        "io_pressure": pressure(read(cg + "/io.pressure")),
        "cpu": kv(read(cg + "/cpu.stat")),
        "current": int(read(cg + "/memory.current")),
        "stat": {k: v for k, v in kv(read(cg + "/memory.stat")).items() if k in STAT_KEYS},
        "host_pressure_memory_after": pressure(read("/proc/pressure/memory")),
        "scope_events_after": kv(read(scope + "/memory.events")),
        "utc_end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "readback_end": {f: read(cg + "/" + f).strip() for f in ["memory.high", "memory.max"]},
    }
    time.sleep(1)
    final["kernel_log"] = kernel_log(unix0 - 1, name)
    if kind == "file":
        drop_file_cache(DATA_FILE)
    if code == "own":
        os.unlink(python)
        os.rmdir(os.path.dirname(python))
    os.rmdir(cg)
    for fn, obj in (("meta.json", meta), ("final.json", final)):
        with open(os.path.join(outdir, fn), "w") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "results/runs"))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--only", help="comma-separated config names")
    ap.add_argument("--max-seconds", type=float, default=150.0)
    ap.add_argument("--churn-ops", type=int, default=200)
    a = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("needs root, or a delegated cgroup subtree it can write to")
    me = read("/proc/self/cgroup").strip()
    if not me.startswith("0::"):
        sys.exit("needs cgroup v2")
    scope = "/sys/fs/cgroup" + me[3:]
    if not scope.endswith(".scope") or "ddmemhigh" not in scope:
        sys.exit("start this through scripts/20-run-matrix.sh (it makes the delegated scope): " + scope)
    for ctl in ("memory", "io"):
        if ctl not in read(scope + "/cgroup.controllers").split():
            sys.exit(ctl + " controller not delegated to " + scope)

    os.makedirs(a.out, exist_ok=True)
    lock = os.open(os.path.join(a.out, ".lock"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(lock, str(os.getpid()).encode())
    stamp = code_stamp()
    try:
        os.sched_setaffinity(0, {0})  # keep the sampler on CPU 0
        os.mkdir(scope + "/driver")
        write(scope + "/driver/cgroup.procs", str(os.getpid()))
        write(scope + "/cgroup.subtree_control", "+memory +io")
        only = set(a.only.split(",")) if a.only else None
        for rep in range(1, a.reps + 1):
            for c in CONFIGS:
                if (only and c["name"] not in only) or (not only and not c["default"]):
                    continue
                if rep > c["reps"]:
                    continue
                run = f"{c['name']}-r{rep}"
                outdir = os.path.join(a.out, run)
                if os.path.exists(outdir):
                    sys.exit("refusing to overwrite " + outdir)
                t = time.time()
                fin = run_one(scope, run, c, rep, outdir, stamp,
                              c["seconds"] or a.max_seconds, a.churn_ops)
                print(f"{time.strftime('%H:%M:%SZ', time.gmtime())} {run}: rc={fin['returncodes']}"
                      f" events={fin['events']} peak={fin['peak'] / MIB:.1f}MiB"
                      f" wall={time.time() - t:.1f}s", flush=True)
    finally:
        os.close(lock)
        os.unlink(os.path.join(a.out, ".lock"))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit("stopped by SIGTERM"))
    main()
