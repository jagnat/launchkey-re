# 18 — First offline musical-table find: the velocity curves

Per the note-17 plan, the goal this session was to make progress on the *musical*
engine **without hardware** — pure static analysis. We found a clean, tweakable
table and, more importantly, its entire code path. This note records both the
finding and the *method*, because the method generalises to scales/chords/arp.

## The method: pattern-scan → structure → xref → decompile

This is the offline analogue of the palette hunt's "flash and look" loop, but every
step is deterministic and runs on the laptop:

1. **Fingerprint by shape.** Musical data has recognisable numeric *shape*. Scales
   are short ascending semitone runs (`0,2,4,5,7,9,11`); velocity curves are long
   monotonic `0..127 → 0..127` maps; chords are tiny triads (`0,4,7`). We scanned
   the image (`scripts/scan_tables.py`) for byte runs matching those shapes rather
   than reading disassembly. Cheap, and it surfaces candidates by *meaning*.
2. **Confirm the structure.** The strongest hit was a cluster at flash
   `0x0801a158`, spaced `0x80` apart, each a 128-byte monotonic `0..127`→`0..127`
   map passing near identity (in 64 → out ~62). That is the textbook layout of a
   **velocity response curve LUT**, not a scale (a scale-quantiser would have
   regular *flat spots* where out-of-scale notes collapse onto the same note;
   these don't).
3. **Find who reads it (xref).** We searched the whole image for the little-endian
   pointer to the base, `58 a1 01 08` → found **exactly one** literal-pool word at
   flash `0x080127dc`. One xref = one consumer. (Flat `objdump` mis-parses this
   region because the pointer sits in a literal pool amid code; this code/data
   ambiguity is exactly why note 17 wanted a real disassembler.)
4. **Decompile in Ghidra (headless).** `tools/ghidra_scripts/VelocityCurve.java`
   (run via `analyzeHeadless tools/ghidra_proj LKMini -process
   '<bin>' -noanalysis -postScript VelocityCurve.java`) pulls the consumer
   function, its callers, and their RAM/flash refs into
   `notes/ghidra-velocity.txt`. That gave us the semantics for free.

## What the table actually is

`scripts/scan_tables.py` + the dump show **3 velocity-curve *sets* at flash
`0x0801a158` (file offset `0x12158`), 0x300 bytes total**, ending exactly where a
function prologue (`70 b5 04 46` = `push {r4,r5,lr}`) begins at `0x0801a458`:

| set | channel 0 (flash) | channel 1 (flash) | character (out @ in=64) |
|-----|-------------------|-------------------|--------------------------|
| 0   | `0x0801a158`      | `0x0801a1d8`      | ~62  → **≈ linear**      |
| 1   | `0x0801a258`      | `0x0801a2d8`      | ~92  → **soft / boost low velocities** |
| 2   | `0x0801a358`      | `0x0801a3d8`      | ~109 → **steep / hard, very easy to max out** |

Each set is a **pair** of 128-byte maps (two input streams — almost certainly the
two velocity domains the device has, e.g. **keys vs pads**). All clamp to ~127 at
the top, as a velocity curve must.

## The code path (the real prize)

From `notes/ghidra-velocity.txt`:

- **`DAT_080127dc` = `0x0801a158`** (table base); **`DAT_080127d8` = `0x20002128`**
  (RAM settings struct). The selected curve lives at `base + index*0x100`, and each
  index registers *two* 0x80 tables (the channel pair).
- **`FUN_08012608` — apply().** Reads `state[0]` (and `state[2]`); if `< 3`, hands
  the curve pair to `thunk_FUN_0800f8e0(channel, ptr, 0x80)` for channels 1/2/3.
  If the index is `3`, it passes `(…, 0, 0)` = **no table = fixed/linear** velocity.
  So the user setting is *0,1,2 = three curves; 3 = off/fixed.*
- **`FUN_080126fc` — set().** Clamps the new value to ≤3, stores it at `state+2`,
  calls `apply()`, then lights an LED via the note-12 descriptor layer
  (`*(desc+0xf) |= 1`). This is the per-setting handler (SysEx / button).
- **`FUN_0801267c` — apply-all().** The global settings-restore routine: re-applies
  the curve plus many sibling settings from `state+1,3,4,5,6,0xe`. `state+4` indexes
  a separate 3-entry 16-bit table `DAT_080127f0 = {0x0000, 0x5555, 0xaaaa}` — another
  small knob to chase later.

So `0x20002128` is the **device settings struct in RAM**, and we now have one field
decoded (velocity-curve index) plus pointers to the rest.

## Why this matters / what's next

- This is the first proof that the **note-17 offline loop works**: we located a
  musical table *and* its meaning with zero hardware.
- It's a ready **easy win**: editing the curve bytes (or the default index) is the
  same flash-a-`.syx` operation as the palette recolour. Concrete idea: flatten
  set 0 to a true identity ramp, or make set 2 a gentle curve.
- **Verification plan (when hardware returns):** play fixed-force notes and
  **capture the USB-MIDI note-on velocity** — exact, programmatic, no eyeballing
  (the audio-domain analogue of the palette confirmation). Build a small
  `scripts/midi_capture.py` (rtmidi is already installed) for this.
- The settings struct at `0x20002128` is the thread to pull next: decoding its
  other fields walks us straight into the arp / chord / scale settings.

## Artifacts
- `scripts/scan_tables.py` — reusable musical-shape scanner (scales, chords, curves).
- `tools/ghidra_scripts/VelocityCurve.java` — xref+decompile of LUT consumers.
- `notes/ghidra-velocity.txt` — decompilation output.
- `tools/svd/STM32F401.svd` — fetched for the upcoming SVD-Loader peripheral pass.
