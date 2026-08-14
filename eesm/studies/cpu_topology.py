#!/usr/bin/env python
"""Identify performance vs efficient cores by measuring them, and suggest a mask.

Intel hybrid parts expose P-cores and E-cores as ordinary logical CPUs and
nothing in the OS labels them. Reading per-CPU maximum frequency does not work
on Windows -- psutil reports the same advertised maximum for every CPU -- so
this pins a fixed workload to each logical CPU in turn and times it. P-cores
finish measurably sooner. That is empirical and needs no downloads.

Run it on the machine that will do the work; enumeration order is a firmware
choice and should never be assumed from a datasheet.

    python eesm/studies/cpu_topology.py
    python eesm/studies/cpu_topology.py --reps 9   # noisier machine, more reps
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time


#: How much the between-cluster gap must exceed the worst within-cluster gap
#: before a split is called real. Tuned so a genuinely noisy 8P+12E part is
#: still detected while a homogeneous part and a single slow outlier are not.
BIMODALITY_MARGIN = 1.25


def compress(cpus: list[int]) -> str:
    """[8,9,10,11,16] -> '8-11,16'"""
    if not cpus:
        return ""
    cpus = sorted(cpus)
    out, start, prev = [], cpus[0], cpus[0]
    for c in cpus[1:]:
        if c == prev + 1:
            prev = c
            continue
        out.append(f"{start}-{prev}" if prev > start else f"{start}")
        start = prev = c
    out.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ",".join(out)


def mask_of(cpus: list[int]) -> int:
    m = 0
    for c in cpus:
        m |= 1 << c
    return m


def _bench_once() -> float:
    """A small fixed FP workload that stays in cache. Returns seconds."""
    import numpy as np
    a = np.random.default_rng(0).random((96, 96))
    b = a.copy()
    t = time.perf_counter()
    for _ in range(60):
        b = a @ b
        b /= (np.abs(b).max() + 1e-300)          # keep it numerically bounded
    return time.perf_counter() - t


def measure_cores(reps: int) -> dict[int, float] | None:
    """Min-of-reps seconds per logical CPU. Min resists background interference."""
    try:
        import psutil
    except ImportError:
        return None
    proc = psutil.Process()
    original = proc.cpu_affinity()
    n = psutil.cpu_count(logical=True) or 0
    times: dict[int, float] = {}
    try:
        for cpu in range(n):
            try:
                proc.cpu_affinity([cpu])
            except Exception:
                continue
            _bench_once()                          # warm up, ignore
            times[cpu] = min(_bench_once() for _ in range(reps))
            print(f"  cpu{cpu:>3}  {times[cpu]*1000:7.1f} ms", flush=True)
    finally:
        try:
            proc.cpu_affinity(original)
        except Exception:
            pass
    return times


def split_by_largest_gap(times: dict[int, float]) -> tuple[list[int], list[int], float]:
    """Cluster into fast and slow at the largest relative gap in sorted times."""
    ordered = sorted(times.items(), key=lambda kv: kv[1])
    vals = [v for _, v in ordered]
    best_i, best_ratio = None, 1.0
    # only consider splits away from the extremes, so one noisy core cannot define it
    for i in range(1, len(vals)):
        ratio = vals[i] / vals[i - 1]
        if ratio > best_ratio:
            best_ratio, best_i = ratio, i
    if best_i is None:
        return [c for c, _ in ordered], [], 1.0
    fast = sorted(c for c, _ in ordered[:best_i])
    slow = sorted(c for c, _ in ordered[best_i:])

    # Guard against calling noise a hybrid split. A real P/E boundary is
    # bimodal: the gap between clusters dwarfs every gap inside them, and both
    # clusters hold more than one core. Two cores that differ only because one
    # was busier must not be reported as different core types.
    within = [vals[i] / vals[i - 1] for i in range(1, len(vals)) if i != best_i]
    worst_within = max(within) if within else 1.0
    if min(len(fast), len(slow)) < 2 or best_ratio < worst_within * BIMODALITY_MARGIN:
        return fast, slow, 1.0

    return fast, slow, best_ratio


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=5,
                    help="timing repetitions per CPU; raise on a busy machine")
    ap.add_argument("--min-ratio", type=float, default=1.15,
                    help="fast/slow gap needed to call the part hybrid")
    args = ap.parse_args()

    try:
        import psutil
    except ImportError:
        print("psutil is required: pip install psutil")
        return 2

    logical = psutil.cpu_count(logical=True)
    physical = psutil.cpu_count(logical=False)
    print(f"logical CPUs  : {logical}")
    print(f"physical cores: {physical}")
    print(f"SMT           : {'yes' if logical != physical else 'no'}")

    print("\nCurrent load (1 s):")
    util = psutil.cpu_percent(interval=1.0, percpu=True)
    for i, u in enumerate(util):
        print(f"  cpu{i:>3} {u:5.1f}% {'#' * int(u / 5)}")
    busy = sum(util) / 100.0
    print(f"\n  total load ~= {busy:.1f} cores of {logical}; "
          f"~{logical - busy:.1f} cores of headroom")
    if busy > logical * 0.5:
        print("  NOTE: this machine is heavily loaded. The measurement below will be "
              "noisy; raise --reps or retry when quieter.")

    print(f"\nTiming a fixed workload on each CPU (min of {args.reps}); "
          "lower is faster:")
    times = measure_cores(args.reps)
    if not times:
        print("measurement unavailable")
        return 2

    fast, slow, ratio = split_by_largest_gap(times)
    med_fast = statistics.median(times[c] for c in fast) if fast else 0.0
    med_slow = statistics.median(times[c] for c in slow) if slow else 0.0

    print()
    if slow and ratio >= args.min_ratio:
        print(f"hybrid detected: largest gap {ratio:.2f}x")
        print(f"  faster cores ({len(fast)}): {compress(fast)}   "
              f"median {med_fast*1000:.1f} ms")
        print(f"  slower cores ({len(slow)}): {compress(slow)}   "
              f"median {med_slow*1000:.1f} ms")
        print(f"  slower cores run at ~{med_fast/med_slow*100:.0f}% of the faster "
              "cores' throughput")
        target = slow
        why = "the slower (efficient) cores, leaving the fast ones free"
    else:
        print(f"no clear hybrid split (largest gap {ratio:.2f}x < {args.min_ratio}).")
        print("Either the part is homogeneous, the split was not bimodal enough to "
              "distinguish from noise, or background load masked it. Retry with "
              "--reps 9 on a quieter machine, or run Sysinternals 'Coreinfo -c' "
              "and pass --cpu-affinity explicitly.")
        print("NOT guessing a mask.")
        return 1

    print(f"\nTo run a background study on {why}:")
    print(f"  --cpu-affinity {compress(target)} --workers {len(target)} "
          "--priority below-normal")
    print(f"  dependency-free: start /affinity {mask_of(target):X} /belownormal ...")
    print("\nIf the machine is already busy, use fewer workers than cores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
