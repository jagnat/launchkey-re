#!/usr/bin/env python3
"""Map STM32 peripheral usage by scanning the image for literal-pool constants
that fall in the MMIO range, bucketed by the STM32F401 SVD.

Cortex-M code loads a peripheral base (e.g. TIM1 = 0x40010000) as a 32-bit word in
a literal pool, then accesses registers at base+offset. So scanning word-aligned
LE32 values in [0x40000000, 0x50040000) and matching them against the SVD tells us
which peripherals are used and which functions reference them — no Ghidra needed.
(Caveat: addresses built via movw/movt pairs won't appear as a contiguous word;
this catches the literal-pool ones, which dominate in HAL builds.)

Outputs re/peripherals.tsv (one row per hit) and prints a usage summary.
"""
import sys, os, struct, xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
BIN = os.path.join(ROOT, "firmware", "launchkey-mini-mk3_v1.2-build461.syx.bin")
SVD = os.path.join(ROOT, "tools", "svd", "STM32F401.svd")
FUNCS = os.path.join(ROOT, "re", "functions.tsv")
BASE = 0x08008000
MMIO_LO, MMIO_HI = 0x40000000, 0x50040000

def parse_svd():
    """-> (sorted list of (base, name), {name: {offset: reg}})."""
    tree = ET.parse(SVD)
    ns = ""  # this SVD has no namespace
    periphs, regs = [], {}
    raw = {}
    for p in tree.iter("peripheral"):
        name = p.findtext("name")
        base = p.findtext("baseAddress")
        derived = p.get("derivedFrom")
        rmap = {}
        rs = p.find("registers")
        if rs is not None:
            for r in rs.iter("register"):
                off = r.findtext("addressOffset")
                rn = r.findtext("name")
                if off is not None and rn is not None:
                    rmap[int(off, 0)] = rn
        raw[name] = (int(base, 0), derived, rmap)
    # resolve derivedFrom register maps
    for name, (base, derived, rmap) in raw.items():
        if not rmap and derived and derived in raw:
            rmap = raw[derived][2]
        periphs.append((base, name))
        regs[name] = rmap
    periphs.sort()
    return periphs, regs

def build_valid(periphs, regs):
    """Map of exact valid MMIO addresses -> (peripheral, register-name).
    Only exact base or known-register addresses count, to reject float/int
    constants that merely fall inside the 0x4xxxxxxx range."""
    valid = {}
    for base, name in periphs:
        valid.setdefault(base, (name, "BASE"))
        for off, rn in regs.get(name, {}).items():
            valid.setdefault(base + off, (name, rn))
    return valid

def periph_of(valid, v):
    return valid.get(v)

def load_funcs():
    funcs = []
    if os.path.exists(FUNCS):
        for ln in open(FUNCS):
            if ln.startswith("#") or not ln.strip():
                continue
            c = ln.rstrip("\n").split("\t")
            funcs.append((int(c[0], 16), int(c[2]), c[1]))  # addr, size, name
    funcs.sort()
    return funcs

def fn_of(funcs, addr):
    """Function containing addr, else the nearest preceding function (literal
    pools follow the function that uses them). Capped so we don't over-reach."""
    prev = None
    for fa, sz, nm in funcs:
        if fa <= addr < fa + sz:
            return nm
        if fa > addr:
            break
        prev = (fa, sz, nm)
    if prev and addr - (prev[0] + prev[1]) < 0x40:
        return prev[2] + "~"   # ~ = attributed via trailing literal pool
    return "?"

def main():
    periphs, regs = parse_svd()
    valid = build_valid(periphs, regs)
    funcs = load_funcs()
    data = open(BIN, "rb").read()
    rows = []
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if MMIO_LO <= v < MMIO_HI:
            res = periph_of(valid, v)
            if not res:
                continue
            name, reg = res
            flash = BASE + off
            rows.append((flash, v, name, reg, fn_of(funcs, flash)))

    # write tsv
    out = os.path.join(ROOT, "re", "peripherals.tsv")
    with open(out, "w") as f:
        f.write("# flash_addr\tvalue\tperipheral\tregister\tfunction\n")
        for flash, v, name, reg, fn in rows:
            f.write(f"0x{flash:08X}\t0x{v:08X}\t{name}\t{reg}\t{fn}\n")

    # summary
    byp = defaultdict(lambda: [0, set()])
    for flash, v, name, reg, fn in rows:
        byp[name][0] += 1
        if fn != "?":
            byp[name][1].add(fn)
    print(f"{len(rows)} MMIO literals across {len(byp)} peripherals -> {out}\n")
    print(f"{'peripheral':22s} {'refs':>4s}  functions")
    for name in sorted(byp, key=lambda n: -byp[n][0]):
        cnt, fns = byp[name]
        fl = ", ".join(sorted(fns)[:6]) + (" ..." if len(fns) > 6 else "")
        print(f"{name:22s} {cnt:4d}  {fl}")

if __name__ == "__main__":
    main()
