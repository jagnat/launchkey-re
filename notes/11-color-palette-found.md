# 11 — The colour palette (and the likely session-idle colour)

## Breakthrough via Novation's own software
Components (`tools/components-main.js`) contains two reference tables we extracted:
- **Custom-mode swatches**: `cyan {index:10, rgb:[52,175,250]}`, `blue {index:11,
  rgb:[52,87,250]}`, … (matches the configurator the user described).
- **A named colour enum**: `Off=0, DimWhite=1, NeutralWhite=2, BrightWhite=3, …`.

That enum gave a structural fingerprint for the firmware's own palette: it must
begin `(0,0,0)` then **three increasing greys** (R=G=B) for Dim/Neutral/Bright white.

## Found the firmware palette by that signature
Scanning the image for `[0,0,0]` followed by three grey entries hit exactly one
place: **`0x0801C250`** (file offset `0x14250`), a **128-entry × 4-byte (R,G,B,pad)**
table — the device's velocity→RGB palette.
```
[0] 0,0,0   [1] 63,63,63   [2] 127,127,127   [3] 255,255,255   (off + 3 whites)
[4..] blue family, cyan family, green, ... in groups of 4 (light/full/half/dim)
```
Full dump: `notes/palette-v1.2.txt`. Selected entries:
```
[ 5] 0,0,255      pure blue
[12] 47,175,255   <-- ≈ Components "cyan" swatch (52,175,250)  ← likely SESSION idle
[13] 0,255,255    pure cyan
[44] 255,31,47    warm red
[45] 255,0,0      pure red
[46] 127,0,0      half red  (muted / night-friendly)
[47] 63,0,0       dim red
```

## Why index 12 is the prime suspect for "session blue"
The user perceives the standalone Session idle as a cyan-ish blue and matched it to
Components' "cyan" swatch `(52,175,250)`. The only palette entry close to that is
**[12] = (47,175,255)**. So the session idle almost certainly renders palette
index 12 (whether it writes the velocity 12, or a hardcoded RGB equal to entry 12).

## Two ways to make the patch
**A. Palette remap (easy, ~3 bytes).** Overwrite entry **12** at file offset
`0x14250 + 12*4 = 0x14280` with a red, e.g. `127,0,0`. Pros: trivial, we already
know the location, instantly testable. Con: changes colour-slot 12 *everywhere*
it's used (custom modes / DAW clips that use that exact colour) — negligible for a
mostly-standalone user.

**B. Session-default index (surgical).** Find where the session-idle code writes the
constant `12` (or sets that colour) to the pad buffer and change only that to a red
index (e.g. 46). Pros: affects only the session idle. Con: needs more tracing.

## Verification plan (before trusting it)
Flashing is reversible (note 08). Recommended:
1. No-op round-trip first: `xkey decode` → `xkey encode` stock, confirm device accepts.
2. Apply route A (entry 12 → red), flash, look: if Session idle turns red, confirmed.
   If not, the idle uses a different index — try the next-closest (e.g. 4, 8, 13).
3. Check for an app self-CRC before/while doing this.

## Patch location quick-ref
```
palette base (VA)   0x0801C250
file offset         0x14250
entry stride        4 bytes (R,G,B,pad)
entry 12 file off   0x14280   bytes now: 2F AF FF 00  -> set to e.g. 7F 00 00 00
```
