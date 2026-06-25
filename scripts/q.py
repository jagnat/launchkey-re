#!/usr/bin/env python3
"""Fast, low-token firmware query tool over the pre-exported re/ corpus.

NO Ghidra launch. Reads re/functions.tsv, re/xrefs.tsv, re/strings.tsv and slices
re/firmware.c. Regenerate the corpus (after renames) with ImportSymbols+ExportCorpus.

Usage:
  q.py fn <name|0xADDR>     function: signature + callers + callees + its decompiled C
  q.py callers <name|addr>  who calls it
  q.py callees <name|addr>  what it calls
  q.py xref <0xADDR>        every reference TO an address (e.g. a data/table addr)
  q.py grep <regex>         search function names + signatures
  q.py str <regex>          search strings
  q.py addr <0xADDR>        identify the function/data at or containing an address
"""
import sys, os, re

RE = os.path.join(os.path.dirname(__file__), "..", "re")

def rows(fn):
    p = os.path.join(RE, fn)
    if not os.path.exists(p):
        sys.exit(f"missing {p} — run ImportSymbols+ExportCorpus first")
    out = []
    for ln in open(p):
        if ln.startswith("#") or not ln.strip():
            continue
        out.append(ln.rstrip("\n").split("\t"))
    return out

def load_funcs():
    by_addr, by_name = {}, {}
    for r in rows("functions.tsv"):
        # addr name size ncallers ncallees cline nclines signature
        d = dict(addr=r[0], name=r[1], size=r[2], ncallers=r[3], ncallees=r[4],
                 cline=int(r[5]), nclines=int(r[6]), sig=r[7] if len(r) > 7 else "")
        by_addr[r[0].lower()] = d
        by_name[r[1]] = d
    return by_addr, by_name

def resolve(tok):
    by_addr, by_name = load_funcs()
    if tok in by_name:
        return by_name[tok]
    t = tok.lower()
    if not t.startswith("0x"):
        t = "0x%08x" % int(tok, 16) if re.fullmatch(r"[0-9a-fA-F]+", tok) else t
    t = "0x%08x" % int(t, 16) if t.startswith("0x") else t
    return by_addr.get(t)

def slice_c(d):
    p = os.path.join(RE, "firmware.c")
    lines = open(p).read().splitlines()
    s = d["cline"] - 1
    return "\n".join(lines[s:s + d["nclines"]])

def cmd_fn(tok):
    d = resolve(tok)
    if not d:
        sys.exit(f"no function '{tok}' (try: q.py grep {tok})")
    a = d["addr"].lower()
    print(f"{d['name']}  @ {d['addr']}  size={d['size']}  callers={d['ncallers']} callees={d['ncallees']}")
    print(f"  {d['sig']}")
    callers = [(x[0], x[1]) for x in rows("xrefs.tsv") if len(x) >= 5 and x[2].lower() == a and x[4] == "call"]
    callees = [(x[2], x[3]) for x in rows("xrefs.tsv") if len(x) >= 5 and x[0].lower() == a and x[4] == "call"]
    if callers:
        print("  callers: " + ", ".join(sorted({c[1] for c in callers})))
    if callees:
        print("  callees: " + ", ".join(sorted({c[1] for c in callees})))
    print("\n" + slice_c(d))

def cmd_dir(tok, want_callers):
    d = resolve(tok)
    a = (d["addr"] if d else tok).lower()
    a = "0x%08x" % int(a, 16) if a.startswith("0x") else a
    seen = set()
    for x in rows("xrefs.tsv"):
        if len(x) < 5 or x[4] != "call":
            continue
        if want_callers and x[2].lower() == a:
            seen.add(f"{x[0]} {x[1]}")
        if not want_callers and x[0].lower() == a:
            seen.add(f"{x[2]} {x[3]}")
    print("\n".join(sorted(seen)) or "(none)")

def cmd_xref(tok):
    a = "0x%08x" % int(tok, 16)
    hit = [x for x in rows("xrefs.tsv") if len(x) >= 5 and x[2].lower() == a.lower()]
    for x in hit:
        print(f"{x[0]}  {x[1]:32s}  {x[4]}")
    if not hit:
        print("(no references)")

def cmd_grep(pat):
    rx = re.compile(pat, re.I)
    for r in rows("functions.tsv"):
        if rx.search(r[1]) or (len(r) > 7 and rx.search(r[7])):
            print(f"{r[0]}  {r[1]:32s}  {r[7] if len(r)>7 else ''}")

def cmd_str(pat):
    rx = re.compile(pat, re.I)
    for r in rows("strings.tsv"):
        if rx.search(r[1]):
            print(f"{r[0]}  {r[1]}")

def cmd_addr(tok):
    a = int(tok, 16)
    best = None
    for r in rows("functions.tsv"):
        fa = int(r[0], 16); sz = int(r[2])
        if fa <= a < fa + sz:
            best = r
    if best:
        off = a - int(best[0], 16)
        print(f"inside {best[1]} @ {best[0]} (+0x{off:x})  {best[7] if len(best)>7 else ''}")
    else:
        print("not inside any known function; check re/data.tsv / strings.tsv")

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    c, arg = sys.argv[1], sys.argv[2]
    {"fn": cmd_fn,
     "callers": lambda t: cmd_dir(t, True),
     "callees": lambda t: cmd_dir(t, False),
     "xref": cmd_xref, "grep": cmd_grep, "str": cmd_str, "addr": cmd_addr,
     }.get(c, lambda _: sys.exit(__doc__))(arg)

if __name__ == "__main__":
    main()
