#!/usr/bin/env python3
"""Static scan of the firmware image for musical interval tables.

We look for byte runs that "smell" like scale / chord interval data:
  - small values (semitone offsets live in roughly 0..24)
  - locally monotonic non-decreasing runs (scales ascend: 0,2,4,5,7,9,11)
  - and we directly fingerprint a library of known scale/chord shapes.

Output is reported in BOTH file offset and flash address (base 0x08008000)
so findings can be jumped to in Ghidra/objdump.
"""
import sys

BASE = 0x08008000
BIN = sys.argv[1] if len(sys.argv) > 1 else "firmware/launchkey-mini-mk3_v1.2-build461.syx.bin"

data = open(BIN, "rb").read()
print(f"# {BIN}: {len(data)} bytes, flash {BASE:#x}..{BASE+len(data):#x}\n")

# --- 1. Fingerprint known interval shapes (as semitone-offset byte sequences) ---
# Scales are given as offsets from the root within one octave.
KNOWN = {
    "major (ionian)":        [0, 2, 4, 5, 7, 9, 11],
    "natural minor":         [0, 2, 3, 5, 7, 8, 10],
    "harmonic minor":        [0, 2, 3, 5, 7, 8, 11],
    "melodic minor":         [0, 2, 3, 5, 7, 9, 11],
    "dorian":                [0, 2, 3, 5, 7, 9, 10],
    "phrygian":              [0, 1, 3, 5, 7, 8, 10],
    "lydian":                [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":            [0, 2, 4, 5, 7, 9, 10],
    "locrian":               [0, 1, 3, 5, 6, 8, 10],
    "major pentatonic":      [0, 2, 4, 7, 9],
    "minor pentatonic":      [0, 3, 5, 7, 10],
    "blues":                 [0, 3, 5, 6, 7, 10],
    "whole tone":            [0, 2, 4, 6, 8, 10],
    "chromatic":             [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "major triad":           [0, 4, 7],
    "minor triad":           [0, 3, 7],
    "dim triad":             [0, 3, 6],
    "aug triad":             [0, 4, 8],
    "maj7":                  [0, 4, 7, 11],
    "min7":                  [0, 3, 7, 10],
    "dom7":                  [0, 4, 7, 10],
}

def find_all(hay, needle):
    out, start = [], 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out

print("== known interval-shape fingerprints (exact byte match) ==")
hits = 0
for name, seq in KNOWN.items():
    b = bytes(seq)
    # only flag shapes long enough to be non-coincidental (>=4 bytes)
    if len(b) < 4:
        continue
    for off in find_all(data, b):
        hits += 1
        print(f"  {name:22s} @ off {off:#07x}  flash {BASE+off:#010x}  {seq}")
if not hits:
    print("  (no exact multi-byte shape matched)")

# --- 2. Generic candidate scan: runs of small, non-decreasing bytes ---
# A scale table is a short ascending run of small values; relax to catch
# arbitrary/modified scales and tables stored as ascending offsets.
print("\n== generic ascending small-value runs (len>=5, vals<=24, last-first<=24) ==")
i = 0
n = len(data)
seen = 0
while i < n:
    j = i
    run = []
    prev = -1
    while j < n and data[j] <= 24 and data[j] >= prev:
        run.append(data[j])
        prev = data[j]
        j += 1
    if len(run) >= 5 and run[0] <= 2 and (run[-1] - run[0]) <= 24 and len(set(run)) >= 4:
        print(f"  @ off {i:#07x}  flash {BASE+i:#010x}  len {len(run):2d}  {run}")
        seen += 1
    i = j if j > i else i + 1
print(f"  ({seen} candidate runs)")
