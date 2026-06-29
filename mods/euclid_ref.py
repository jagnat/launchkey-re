#!/usr/bin/env python3
"""Host reference for the on-device Euclidean generator (Time track).

This is the GROUND TRUTH the Thumb `euclid_compute` in mods/asm/rhythm_decode.s must
match bit-for-bit. The firmware computes the mask live from (k, n, rot); this prints the
expected mask + the arp gap signature so a post-flash MIDI capture can be checked.

Primitive (the one we reuse across tracks): distribute k events across n slots, hit on
slot 0, offset by rot. Even (Bjorklund) distribution via the i*k mod n test.
"""

def euclid(k, n, rot=0):
    if n < 1: n = 1
    if k < 1: k = 1
    if k > n: k = n
    m = 0
    for i in range(n):
        if (i * k) % n < k:
            m |= 1 << ((i + rot) % n)
    return m

def gaps(mask, n, clocks_per_step=6):
    """Clocks between successive hits (1/16 = 6 clocks/step @24PPQN) — what arp capture sees."""
    hits = [i for i in range(n) if (mask >> i) & 1]
    if not hits: return []
    return [((hits[(j + 1) % len(hits)] - hits[j]) % n) * clocks_per_step
            for j in range(len(hits))]

# v1 tracer: cfg[3] 5..10 -> these k at n=16, rot=0 (computed live, supersedes note-22 table)
K_TABLE = [4, 5, 6, 7, 9, 11]

if __name__ == "__main__":
    print("sel  k   n   mask      hits  steps(x=hit)        gaps@1/16")
    for idx, k in enumerate(K_TABLE):
        n = 16
        m = euclid(k, n)
        steps = "".join("x" if (m >> i) & 1 else "." for i in range(n))
        hc = bin(m).count("1")
        print(f" {idx+5}  {k:2d}  {n:2d}  0x{m:04X}   {hc:2d}   {steps}  {gaps(m,n)}")
    # the one stage-2a HW-validated point: E(4,16) must be all-even 24-clk gaps
    assert euclid(4, 16) == 0x1111, "E(4,16) regression"
    assert gaps(euclid(4, 16), 16) == [24, 24, 24, 24], "E(4,16) gap signature regression"
    print("\nself-check OK: E(4,16)=0x1111, gaps=[24,24,24,24] (matches stage-2a HW result)")
