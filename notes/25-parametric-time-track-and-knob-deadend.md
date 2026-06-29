# 25 — Parametric Euclidean Time track, and the knob-control dead end

Checkpoint after turning the Euclidean rhythm from fixed presets into a **live parametric
generator**, validating it on hardware, and then chasing — and ruling out — **physical-knob
control** standalone. The headline: the feature works and is DAW-playable today; the knob
vision turns out not to be a firmware feature we can flip on.

## What works now (and is HW-proven)

`mods/asm/rhythm_decode.s` (detour over `rhythm_decode`@`0x080175B0` → appended
`euclid_compute`) computes the rhythm mask **live**. For `cfg[3] ∈ 5..10` it now reads:

- **k** (hit count) from `cfg[6]` = the **Mutate** field
- **n** (length)    from `cfg[9]` = the **Deviate** field
- rot = 0; `euclid_compute(k,n,rot)` clamps `1 ≤ k ≤ n`, `n ≥ 1`.

Stock rhythms `0..4` stay byte-identical. The key structural fact that made this cheap:
**`arp_cc_in_handler` already stages Mutate/Deviate into `cfg[6]`/`cfg[9]` and then calls
`arp_cfg_apply` → `rhythm_decode`** — so changing those values re-derives the rhythm with no
new plumbing. We only had to make the engine *read* them.

### Validation (DAW-port CC, measured)
Arp latched + chord streaming; sent CCs on the **DAW port** (ch0, `0xB0`):
- `0x5b=5` enables parametric euclid.
- `0x5a` (Mutate→k): value 0 → all `12`-clk gaps (k≈8, sparse); value 127 → all `6`-clk
  (k=16, dense). **Changing only Mutate flipped density → k is live from `cfg[6]`. ✓**
- `0x5d` (Deviate→n): sweeping it changes the pattern. **n is live from `cfg[9]`. ✓**

So: knob-value → CC → `cfg` → `euclid_compute` → correct rhythm, end to end.

## The knob dead end (what we ruled out, and how)

Goal was physical-knob control. We found the rightmost 3 pots send CC `0x1A/0x1B/0x1C` on
**ch16** (`0xBF`) — generic pot CCs, *not* the `0x55–0x5D`/ch0 arp range. Then a ladder of
tests, all negative:

1. Send pot CC `0x1B`/ch16 → no rhythm change (vs `0x5B`/ch0 which always works).
2. Twist physical Mutate, arp latched → no density change.
3. Same, **holding the Arp page** → no change.
4. Sweep **all 8 knobs**, page held → clean `12`s throughout.
5. **Crank Mutate to max, then force a recompute** (`0x5b=5`, which re-reads `cfg[6]`
   without writing it) → still `12`s. This is the decisive one: if the knob had written
   `cfg[6]`, the forced recompute would have read the high value and jumped to `6`s.
6. **Enable DAW/InControl mode** (`9F 0C 7F`) then twist Mutate → still no change.

**Conclusion:** standalone, the knobs are **output-only** — the firmware *emits* knob CCs to
the host but does **not** route them back into the arp. The "knobs do Mutate/Deviate"
behavior the user sees is **Ableton's Launchkey control script** reading the knobs and
bridging them; it lives in Ableton, not the device. There is no firmware switch to enable it.

### Why the gap-measurement was even able to tell us this
k changes are visible because density changes the gap histogram. A subtlety surfaced:
**`cfg[9]` (Deviate) double-duties** — the step engine *also* consumes it as a timing param
(clean alternating `{4,8}` gaps = swing/deviation), independent of our mask. So `cfg[9]` is a
**bad long-term home for n** (the swing artifact rides along). n needs a side-effect-free
field.

## Where this leaves us — the fork

- **A. Accept DAW-CC as v1.** The Time track is fully playable from a host now; move on.
- **C. Pivot control to the pads.** Pads *are* read internally and we own that path
  (`arp_control_handler` → `arp_rhythm_select`, note 23). k/n via pad presses + the live
  pattern view (the planned pad-render). Guaranteed standalone, fully understood. No knobs.
- **D. Build standalone knob→arp routing.** Hook the firmware's internal **pot ADC-scan /
  CC-emit** path (where it reads the pot before sending the CC) and route that value into the
  arp config. This is the original knob vision, standalone — but a fresh RE target
  (the ADC/knob layer), untouched so far.

Recommendation: if knobs are the goal, **scout D** cheaply (locate the pot scan/emit) to size
the hook; otherwise **C** is the pragmatic standalone win.

## Bookkeeping done this session
- Promoted the arp UI/engine cluster to real symbols (`re/symbols.tsv`, regen'd corpus:
  coverage 169→180). The whole press→config→engine chain now reads in plain names
  (`arp_cfg_apply`, `arp_rhythm_select`, `arp_cc_in_handler`, `arp_step_emit`, …). See note 23.
- CLAUDE.md gained the Ghidra-headless Java-21 gotcha (clear the OSGi cache if a Java-24 run
  poisoned it).
- Device currently runs the parametric build, left in euclid mode (`cfg[3]=5`); send
  `B0 5B 00` on the DAW port or reflash stock to restore plain `O`.
