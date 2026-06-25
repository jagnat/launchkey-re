# 07 — Ghidra decompilation & the HAL-handle tracing method

We installed **Ghidra 12.1.2** (Homebrew formula; it bundled its own JDK 21) and
drove it **headless** so every step is scriptable and reproducible.

## Reproducible workflow
```bash
HL=/opt/homebrew/Cellar/ghidra/12.1.2/libexec/support/analyzeHeadless
# 1) import + auto-analyze (raw binary, Cortex-M, load @ 0x08008000)
"$HL" tools/ghidra_proj LKMini \
  -import firmware/launchkey-mini-mk3_v1.2-build461.syx.bin \
  -processor "ARM:LE:32:Cortex" \
  -loader BinaryLoader -loader-baseAddr 0x08008000
# 2) re-open without re-analysis and run a script
"$HL" tools/ghidra_proj LKMini \
  -process launchkey-mini-mk3_v1.2-build461.syx.bin -noanalysis \
  -scriptPath tools/ghidra_scripts -postScript FindLed.java
```
Auto-analysis took **9 seconds** and produced **1,188 functions** with full
decompilation available. Script + raw output live in `tools/ghidra_scripts/` and
`notes/ghidra-led-analysis.txt`.

## The key methodology lesson: HAL hides peripherals behind RAM handles
My first instinct — "find the LED driver by searching for functions that reference
the SPI base address" — found **only one** function, and it referenced *every*
peripheral. That one function is the **central hardware init** (`MX_*_Init`).
Tellingly, `USB_OTG_FS` showed **0** referencing functions, even though the device
is obviously a USB-MIDI device.

Why? **ST's HAL stores each peripheral's base address inside a "handle" struct in
RAM** (`hspi1.Instance = SPI1;` etc.), done once in init. Everywhere else, code
operates on the peripheral *through that RAM handle pointer*. So the raw base
address (`0x40013000`) appears as a literal **only in init** — scanning for it
finds init and nothing else.

**Consequence for RE:** to find who actually *uses* a peripheral, you don't xref the
peripheral base — you xref the **RAM handle address** that init created. That handle
is the real anchor for the data path.

## What the init (FUN_080083bc @ 0x080083bc) told us
Resolving its literal pool gives the device's confirmed hardware:
```
GPIOA 0x40020000   GPIOB 0x40020400   GPIOC 0x40020800   GPIOD 0x40020C00
SPI2  0x40003800   ADC1  0x40012000   DMA2  0x40026400
HAL handle structs in RAM @ 0x20002400 / 0x20002408 (+ sub-structs, e.g. +0x1218)
```
And it bit-bangs GPIO **BSRR** (`+0x18`) lines around the SPI setup:
```
*(GPIOA + 0x18) = 0x100000;     // reset PA4   (a chip-select / latch?)
*(GPIOC + 0x18) = 0x1e000000;   // reset PC9..PC12
*(GPIOC + 0x18) = 0x200;        // set   PC9
*(GPIOD + 0x18) = 0x40000;      // reset PD2
```
GPIO latch/CS lines wrapped around an SPI peripheral is the textbook shape of an
**SPI-driven LED matrix with a GPIO latch** — i.e. the pad RGB LEDs are very likely
streamed over **SPI2** (with **DMA2**), latched by GPIO. (ADC1+DMA2 is the parallel
analog path: knobs / pitch-mod strips.)

> Refinement vs note 06: the *primary* LED SPI looks like **SPI2** (0x40003800),
> which init configures heavily; SPI1 appeared only as a lone literal. We'll confirm
> by following the handle.

## Next step (the actual LED render function)
Trace the **RAM handle at 0x20002400** (and its `+0x1218` SPI sub-handle):
1. xref that RAM address → the functions are the SPI users: init, the ISR/DMA
   complete callback, and the **frame push** (`HAL_SPI_Transmit[_DMA](&handle, fb, n)`).
2. The `fb` argument points at the **LED framebuffer** in RAM (≈ 16 pads × RGB, plus
   the side/function LEDs). Find its writers → that's the "set pad color" logic that
   incoming MIDI ultimately drives.
3. Decompile those and document the framebuffer layout + color encoding.

That gives us everything needed to later light pads from custom firmware.
