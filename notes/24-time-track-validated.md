# 24 — Time track validated: live on-device Euclidean + the DAW-port lesson

Short milestone note. We now have the **first track of the parametric arp** (note 23's
architecture) running and **proven on hardware**: the firmware *computes* Euclidean rhythms
live from (k, n, rot) instead of looking them up. Two things got proven and one important
black-box fact got learned.

## What shipped

- `euclid_compute(k,n,rot)` — a reusable Thumb subroutine (the generator *primitive* the
  Pitch/Octave/Accent tracks will reuse) in `mods/asm/rhythm_decode.s`, appended at
  `0x0801D8AC`. It distributes k hits across n slots by the `i*k mod n` test, hit on slot 0,
  rotated by rot. Host ground-truth = `mods/euclid_ref.py` (same algorithm, prints the
  predicted gap signatures).
- `cc5b-rhythm-clamp-0to10` — an inline patch (`0x0801AC1C`) that replaces the stock CC 0x5b
  Rhythm handler's `tbb` identity-switch (which clamped 1..4) with a clean `1..10` clamp, so
  external MIDI can select the Euclidean presets. Keeper feature *and* our test channel.

Both ride in `mods/build.py` alongside the red-LED patch; stock rhythms 0..4 stay
byte-identical.

## The DAW-port lesson (worth remembering)

An earlier session tried to drive arp Rhythm by sending **CC 0x5b** and called it
"inconclusive." The reason: **the arp CC handler (`FUN_0801aaf0`) listens on the Launchkey
DAW Port, not the MIDI Port.** Sending `B0 5B vv` to the *MIDI* port does nothing; sending it
to the **DAW Port** changes the rhythm immediately. (Note-ons still come *out* on the MIDI
Port — so capture and control are on different ports.) This gives us a no-touch control
channel for any arp parameter the CC handler covers (Mode/Rate/Oct/Latch/Gate/Mutate/
Rhythm/Deviate), which is gold for black-box validation.

## How we validated (measure, don't eyeball)

With Latch + a held chord streaming, we swept `CC 0x5b = 5..10` on the DAW port and read the
clocks-between-note-ons histogram each time. The discriminating fact is *which* gap values
appear (at 1/16 = 6 clocks/step): a wrong computation would put hits in the wrong places and
produce the wrong gap set. Every preset matched `euclid_ref.py`:

| CC | k | predicted gap-set | captured (values) |
|---|---|---|---|
| 5 | 4 | 24×4 | 24 only ✓ |
| 6 | 5 | 24×1 18×4 | 24 + 18 ✓ |
| 7 | 6 | 18×4 12×2 | 18 + 12 ✓ |
| 8 | 7 | 18×2 12×5 | 18 + 12 ✓ |
| 9 | 9 | 12×7 6×2 | 12 + 6 ✓ |
| 10 | 11 | 12×5 6×6 | 12 + 6 ✓ |

Clean monotonic densification (24→18→12→6 as k rises), exactly as even distribution predicts.
Counts are per-cycle; captured counts are a few cycles' worth, so ratios match within the
window. **euclid_compute is correct on real silicon.**

## The seam for next step

Right now `(k,n,rot)` is *cfg-derived* (k from `k_table[cfg[3]-5]`, n=16, rot=0). That's the
deliberate seam: the next mod swaps the source for **3 arp knobs**. Plan — capture which CCs
the rightmost 3 knobs send (on the DAW port now that we know that's the channel), then add a
branch in `FUN_0801aaf0`: when rhythm == euclid, route those 3 CCs to k/n/rot (rescaled)
instead of Mutate/Deviate, and have `euclid_compute` read them. Then the pad-render live
pattern view. Then RE the note-selection engine to extend the primitive to Pitch/Octave.
