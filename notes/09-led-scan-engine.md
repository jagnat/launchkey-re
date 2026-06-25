# 09 — The LED + key scan engine (the answer to "where's the LED code")

Surprise: there is no dedicated "SPI LED driver". The pads' RGB LEDs and the keys
are handled together by a **multiplexed matrix scan** running in a **timer ISR**.
This is the core real-time routine of the whole device.

## How we found it
The HAL-handle hypothesis (note 07) said: don't xref peripheral *bases*, find the
*drivers*. Listing functions that reference SPI2/DMA/TIM1 (excluding the init) gave
4 functions. The big one — **FUN_080095a8** (734 bytes, TIM1) — resolved its literal
pool to:
```
DAT_08009944 = 0x40010010  = TIM1_SR    (status reg)
DAT_0800994c = 0x40020418  = GPIOB_BSRR (atomic pin set/reset)
DAT_08009948 = 0x20002370  = scan state struct in RAM
DAT_08009974 = 19-byte step table: 00 07 04 09 01 02 05 03 06 08 03 07 00 09 02 04 01 05 06
```
Its first act is `if (TIM1_SR bit0 clear) return; TIM1_SR = ~UIF;` — the classic
**timer update ISR** prologue. Confirmed: this is the TIM1 interrupt handler.

## What the ISR does each tick (FUN_080095a8 @ 0x080095a8)
A small state machine (state at `struct+0x64`) advancing a **19-step scan** (step at
`+0x60`, wraps at 18) and a **96-entry column index** (`+0x5c`, wraps at 0x60):

1. **Self-times the scan**: writes `TIM1_ARR` (`piVar2[7]`) from a per-step value, so
   each scan slot has its own duration (used for LED brightness timing).
2. **Drives column-select lines** via `GPIOB_BSRR` (`*piVar3 = 0x400; =0x40000;
   = pattern<<16`) — BSRR's upper half resets pins, lower half sets them, so one
   write both deselects the old column and selects the new one.
3. **Reads analog** for that column: `FUN_08009502(...)` arms an **ADC→DMA** transfer
   (count 4) and `FUN_0800d900()` collects **8×12-bit ADC samples** into a buffer.
   → this is the velocity-sensitive **keybed** + the **8 knobs** being digitised.
4. **Refreshes LED rows**: `FUN_0800d8bc()` / `FUN_0800d9d8()` (called from here) push
   the LED row data for the current column.
5. **PWM brightness**: a phase counter `+0x78 & 0xf` indexes a **16-entry timing
   table** (`DAT_0800998c`) — i.e. **16 brightness levels via time modulation**
   (binary-code modulation / PWM). That's why colours look smooth despite a binary
   GPIO matrix.

## The ADC collector (FUN_0800d900 @ 0x0800d900)
```c
for (ch = 0; ch < 8; ch++)
    dest[scanline*8 + ch] = (adc[ch] & 0xfff) + (column << 16);
// then re-arm DMA2: set mem addr, count=0x3d, enable stream + DMA
```
8 channels × 12-bit = the analog inputs, tagged with the scan column. Confirms
**ADC1 + DMA2** is the input-sense path, interleaved into the same scan.

## Mental model (for the C rebuild)
```
        TIM1 update IRQ  (period reprogrammed every step from a table)
                  │
                  ▼
  FUN_080095a8  ── step++ (0..18) ──┐
     ├─ GPIOB_BSRR: select column   │  one matrix scan slot:
     ├─ ADC+DMA: read keys/knobs     │  drive a column, read its
     ├─ FUN_0800d8bc/_d9d8: LED rows │  sensors, light its LEDs
     └─ phase&0xf → 16-level PWM ────┘
```

## Remaining to fully own the LEDs
- Decompile **FUN_0800d8bc / FUN_0800d9d8** → the exact **GPIO row pins** and how a
  pixel's on/off + brightness bitplane is emitted.
- Find the **LED framebuffer** in RAM (the array those row-drivers read) and who
  **writes** it — that's the "set pad colour" path, ultimately driven by incoming
  MIDI (Note On velocity = colour, Launchpad-style).
- Document the framebuffer layout (pad index → RGB, brightness mapping).

> Why this is great news for a custom firmware: the whole light show is a CubeMX-able
> recipe — one TIM in IRQ mode, a few GPIO ports, ADC+DMA — exactly the kind of
> thing you've built before. We're reversing a known pattern, not a black box.
