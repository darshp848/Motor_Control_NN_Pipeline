#!/usr/bin/env python
"""Report this machine's logical CPUs and suggest an affinity mask.

Intel hybrid parts expose performance and efficient cores as ordinary logical
CPUs; nothing in the OS labels them. The reliable discriminator available from
Python is per-CPU maximum frequency: P-cores turbo higher than E-cores.

Run this on the machine that will do the work. Do not infer the numbering from
a datasheet alone -- enumeration order is a firmware choice.

    python eesm/studies/cpu_topology.py
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import psutil
    except ImportError:
        print("psutil is required: pip install psutil")
        return 2

    logical = psutil.cpu_count(logical=True)
    physical = psutil.cpu_count(logical=False)
    print(f"logical CPUs : {logical}")
    print(f"physical cores: {physical}")
    print(f"hyper-threading: {'yes' if logical != physical else 'no'}")

    freqs = []
    try:
        per = psutil.cpu_freq(percpu=True) or []
        freqs = [f.max for f in per]
    except Exception as exc:
        print(f"per-CPU frequency unavailable ({exc})")

    if freqs and len(set(freqs)) > 1:
        hi = max(freqs)
        p = [i for i, f in enumerate(freqs) if f >= hi - 1e-9]
        e = [i for i, f in enumerate(freqs) if f < hi - 1e-9]
        print(f"\nmax turbo split: {hi:.0f} MHz on {len(p)} CPUs, "
              f"lower on {len(e)}")
        print(f"  likely P-cores: {compress(p)}")
        print(f"  likely E-cores: {compress(e)}")
        target = e
    else:
        print("\nPer-CPU max frequency is uniform or unavailable, so P/E cannot be "
              "split from Python alone.")
        print("Check the part's spec, or run Sysinternals Coreinfo -c, then pass "
              "--cpu-affinity explicitly.")
        target = list(range(max(logical - 4, 1), logical)) if logical else []

    if target:
        mask = 0
        for c in target:
            mask |= 1 << c
        print(f"\nto keep a foreground job (FEMM) on the fast cores, run the study on:")
        print(f"  --cpu-affinity {compress(target)}")
        print(f"  Windows launch equivalent: start /affinity {mask:X} /belownormal ...")

    print("\nCurrent per-CPU utilisation over 1 s:")
    for i, u in enumerate(psutil.cpu_percent(interval=1.0, percpu=True)):
        bar = "#" * int(u / 5)
        print(f"  cpu{i:>3} {u:5.1f}% {bar}")
    return 0


def compress(cpus: list[int]) -> str:
    """[8,9,10,11,16] -> '8-11,16'"""
    if not cpus:
        return ""
    cpus = sorted(cpus)
    out, start, prev = [], cpus[0], cpus[0]
    for c in cpus[1:]:
        if c == prev + 1:
            prev = c; continue
        out.append(f"{start}-{prev}" if prev > start else f"{start}")
        start = prev = c
    out.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ",".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
