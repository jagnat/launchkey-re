# 08 — Flashing a modified image & safety (reference)

## Routes to flash
1. **SysEx (no hardware, preferred)** — patch `.bin`, re-encode to `.syx`
   (`xkey encode --model launchkey-mk3 --build N`), send to the device bootloader
   over MIDI (same path Novation Components uses). Bootloader checks: **device id
   `01 02`** + **CRC32** (xkey computes it). No signature.
2. **SWD (hardware)** — ST-Link/J-Link/Pi-Pico probe on SWD pads. Writes flash
   directly; lets you **dump current flash first** (full backup) and restore
   anything, including the bootloader. Requires opening the case; RDP may block reads.

## Why it's recoverable (the key safety property)
Flash is split:
```
0x08000000  BOOTLOADER (32 KB)  <- SysEx update NEVER writes here
0x08008000  APPLICATION         <- only this region is rewritten
```
A bad app image → device falls back to the **bootloader** (enter with **Octave+ &
Octave− on power-up**) → reflash stock `.syx`. The SysEx route cannot corrupt the
bootloader, so you essentially cannot make an unrecoverable mistake that way.
**Only SWD can brick the bootloader.** Always keep the stock `.syx` as recovery.

## Risks to verify BEFORE patching for real
- **App self-CRC / length check**: the END record had pointer/length-looking bytes;
  confirm whether the bootloader/app verifies an app CRC separate from the transfer
  CRC. If yes, recompute it on patch. Failure mode is reject (safe) or boot-loop
  (recoverable via bootloader).
- **No-op round-trip validation** (do this first, zero risk):
  ```
  xkey decode stock.syx           # -> stock.bin
  xkey encode stock.bin --model launchkey-mk3 --build 461   # -> re-encoded .syx
  # diff re-encoded vs original; flash re-encoded STOCK and confirm device accepts it
  ```
  Proves the decode→edit→encode→flash loop is reversible before we change a byte.

## Patching mechanics
- Small data tweak (e.g. an LED color constant): edit bytes in `.bin`, re-encode.
- Instruction patch: assemble Thumb, splice bytes at the right file offset
  (offset = VA − 0x08008000). Keep size identical to avoid shifting everything.
- Re-encode handles the transfer CRC; mind the app self-CRC (above).

## TODO before first real flash
- [ ] Confirm we can enter the bootloader (Octave±) and that it re-enumerates.
- [ ] No-op round-trip: device accepts a re-encoded **stock** image.
- [ ] Determine app self-CRC situation.
