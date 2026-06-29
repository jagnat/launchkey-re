#!/usr/bin/env python3
"""Auto-classify trivial unnamed functions for bulk symbol naming.

Reads the re/ corpus (functions.tsv + firmware.c) and proposes names for two
high-confidence categories that don't need per-function reading:

  * thunk    -> `j_<callee>`   : <=24 B body whose ONLY call is to a NAMED fn
                                 (a forwarder/veneer). Numeric suffix on dupes.
  * nullsub  -> `nullsub_<addr>`: <=4 B function whose body is exactly `return;`
                                 (a real `bx lr` empty fn; `b .` traps render as
                                 loops, not `return;`, so they're excluded).

NOTE: only <=4 B is treated as empty. A 6-10 B "return;" void fn is often a
memory-barrier/delay stub (dsb;isb;bx lr renders as bare return) with an
ordering side-effect — do NOT call those nullsub.

Re-run after each naming milestone: as core functions get names, more thunks
to them become classifiable.

Usage:
  classify_stubs.py            # dry-run, print proposals + counts
  classify_stubs.py --apply    # merge into re/symbols.tsv (sorted, skips existing)
"""
import re, sys, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM = os.path.join(ROOT, "re/symbols.tsv")
SRC = os.path.join(ROOT, "re/firmware.c")
KW = {"if", "for", "while", "switch", "return", "do", "sizeof"}
CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")


def load_named():
    named = set()
    for ln in open(SYM):
        if ln.startswith("#") or not ln.strip():
            continue
        a, k, n = ln.rstrip("\n").split("\t")
        if k == "func":
            named.add(n)
    return named


def iter_funcs():
    parts = re.split(r"(/\* ==== .*? ==== \*/\n)", open(SRC).read())
    for i in range(1, len(parts), 2):
        hdr = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        m = re.match(r"/\* ==== (\S+) @ (\w+)\s+\((\d+) b, (\d+) callers\)", hdr)
        if m:
            yield m.group(1), m.group(2), int(m.group(3)), body


def classify():
    named = load_named()
    out, cnt = [], Counter()
    for name, addr, size, body in iter_funcs():
        if not name.startswith("FUN_"):
            continue
        bi = body.find("{")
        if bi < 0:
            continue
        code = body[bi + 1:body.rstrip().rfind("}")]
        norm = re.sub(r"\s+", " ", code).strip()
        calls = [x for x in CALL.findall(code) if x not in KW]
        if size <= 24 and len(calls) == 1 and calls[0] in named:
            base = "j_" + calls[0]
            cnt[base] += 1
            nm = base if cnt[base] == 1 else f"{base}_{cnt[base]}"
            out.append((addr, nm, "thunk"))
        elif size <= 4 and not calls and norm == "return;":
            out.append((addr, "nullsub_" + addr.lower(), "nullsub"))
    return out


def main():
    out = classify()
    nth = sum(1 for _, _, k in out if k == "thunk")
    nnu = sum(1 for _, _, k in out if k == "nullsub")
    for a, n, k in sorted(out):
        print(f"0x{a.upper()}\tfunc\t{n}\t# {k}")
    print(f"\n# total={len(out)} thunks={nth} nullsubs={nnu}", file=sys.stderr)
    if "--apply" in sys.argv:
        header, rows = [], {}
        for ln in open(SYM):
            if ln.startswith("#"):
                header.append(ln.rstrip("\n"))
                continue
            if not ln.strip():
                continue
            a, k, n = ln.rstrip("\n").split("\t")
            rows[int(a, 16)] = (a, k, n)
        added = 0
        for a, n, _ in out:
            ai = int(a, 16)
            if ai in rows:
                continue
            rows[ai] = (a, "func", n)
            added += 1
        with open(SYM, "w") as f:
            f.write("\n".join(header) + "\n")
            for ai in sorted(rows):
                a, k, n = rows[ai]
                f.write(f"{a}\t{k}\t{n}\n")
        print(f"# applied: +{added} rows -> {len(rows)} total", file=sys.stderr)


if __name__ == "__main__":
    main()
