# Note 33 — The control-surface scanner (go nuts 6, and the knob path resurfaces)

**Avenue:** coverage — the last flagged lead, the `0x0800F_` module (68 funcs), whose entry
points (`control_claim_*`, `ctrl_feature_write`) we'd named in go-nuts-5. It turned out to be
the single most goal-relevant cluster of the whole arc: **the physical control-surface
scanner** — the pot/strip/pad ADC→value→emit path that note 25 explicitly wanted RE'd for the
knob→arp mod.

## What the module is

`control_surface_scan` (0x0800B8B8) is a **polled task** run from `peripheral_init_all`'s main
loop. Each pass it runs three group scanners and conditions every analog control:

- `pot_scan` (0x0800F06A) — the **8 pots**, ids 0x80+. Reads a 12-bit value, applies a
  deadzone (`<0x259 → 0`, a linear middle region, `>0xdac → max`) and a calibration curve via
  `control_calib_lut`. This is the function behind "turning a knob produces a CC."
- `pitchstrip_scan` (0x0800F4F0) — id **0x36**, center-scaled to 0x8000 (bipolar) → the pitch
  touch strip. (And note that 0x36 is exactly what `control_claim_id36` guards — the claim
  predicates and the scanners line up by id.)
- `control_velocity_scan` (0x0800F260) — low ids (0+), strike/velocity detection with three
  parallel state arrays → pad/key velocity.

The raw read is `control_raw_read` (0x0800A9E0): it returns a 12-bit value plus a mode nibble
(`& 0xf000`) and applies hysteresis on the low bits. That mode nibble is the same `0x2000`/
`0x3000` field `route_is_incontrol` keyed on (note 28) — so the control identity threads all
the way from the ADC to the MIDI encoder.

The conditioned value is published by **`control_value_emit`** (0x0800F840): it walks a
subscriber callback list (`DAT_0800f8c0`) and hands each `(id, value)`. `control_value_release`
(0x0800F884) does the same for releases.

## Why this is the answer to the note-25 dead end

Note 25 concluded the physical knobs are "output-only standalone" — they emit pot CCs that
never reach the arp, and only Ableton's script makes them drive Mutate/Deviate. This module
shows the *mechanism* and corrects the framing: the knobs **are** scanned and published
internally — the arp just **isn't on `control_value_emit`'s subscriber list**. The value flows
to the USB-CC-out path (which the host bridges back to the arp), not to `arp_cfg_apply`.

So a standalone knob→arp mod is now concretely buildable, and we can see exactly where:

- **Option A:** register an extra subscriber in `control_value_emit`'s list (`DAT_0800f8c0`)
  that, for the chosen pot id, calls `arp_cfg_apply` (or writes the euclid k/n cfg fields).
- **Option B:** have the relevant pot's route carry the arp's `(class, index)` so the existing
  publish path lands on it.

Either way the two ends are now mapped: scanner → `control_value_emit` (here) and
`arp_cfg_apply` / the euclid engine (notes 22-25). The MAP's OPEN-FORK option D is marked done.

## A recurring gotcha, now nailed down: Thumb veneer phantoms

`classify_stubs.py` kept proposing thunks at addresses like `08008d4e/d50/d56` and `0801bae4`.
These are **Thumb veneers** that `ExportCorpus` lists as functions but `ImportSymbols` can't
rename (no `Function` object) — so `--apply` writes rows that never take effect, and the named
count comes up short of the symbols.tsv func-row count (the reliable detector: `grep -c '\tfunc\t'`
vs the regen's `funcs=`). Fix applied: removed the dead rows and expanded the `PHANTOM`
skip-set; `classify_stubs.py` now reports 0 proposals, and func-rows == named count.

## Bookkeeping & where things stand

- +8 funcs, but **+2.6% bytes** (these scanners are large: 570/410/372 B) → 328/1233 (26.6%),
  35.0% code bytes.
- MAP: new "Control-surface scanner" section; coverage line; OPEN-FORK option D closed.
- Session arc (notes 26-33): **180 → 328 functions (14.6% → 26.6%)**, 25.9% → 35.0% bytes.
  The full MIDI control plane is now mapped end to end — physical ADC scan → condition → emit →
  transform (`ctrl_in_*`) → store → publish → encode/smooth (`ctrl_out_*`) → `midi_tx` → wire —
  plus the scale/chord engine, the arp engine (earlier), and complete peripheral coverage.
- Still open for a future session: the ~50 small `0x0800F_` state helpers, the `0x08010_`
  page-UI cluster, and actually *building* the knob→arp subscriber mod now that the seam is known.
