# 05 — Locating the binary in memory (the load address)

We have 88,088 raw bytes. To disassemble them we must know **where they live in the
address space** — pick the wrong base and every absolute pointer/branch is wrong.
For a Cortex-M chip there's a reliable trick: the **vector table**.

## Cortex-M vector table = free ground truth
The first words of a Cortex-M image are a fixed table:
```
word[0] = Initial Stack Pointer   (an SRAM address, 0x2000_xxxx)
word[1] = Reset handler           (a flash address, odd = Thumb)
word[2..] = NMI, HardFault, ...   (flash addresses, odd)
```
Reading our image's first 16 words:
```
[0] Initial SP  = 0x2000FFF8   <- SRAM. 0x2000FFF8 ≈ top of a 64 KB SRAM
[1] Reset       = 0x0801D251   <- flash, odd (Thumb) ✓
[2] NMI         = 0x0801D0F1
[3] HardFault   = 0x0801D0F3
... SVCall/PendSV/SysTick all 0x0801D0Fx
```
Two facts fall out immediately:
- **SRAM is 64 KB** (`0x20000000`–`0x2000FFFF`) → consistent with **STM32F401**.
- All handler pointers cluster at `0x0801D0F1…0x0801D251` → the image lives in
  flash ending somewhere above `0x0801D251`.

## Deriving the base from a constraint
Every handler address must fall **inside** the loaded image `[base, base+size)`,
size = `0x15818`. With handlers spanning `0x0801D0F1…0x0801D251`:
```
base ≤ 0x0801D0F1     (lowest handler is inside)
0x0801D251 < base + 0x15818   →  base > 0x08007A39
```
On STM32F401 the flash is sectored (16K,16K,16K,16K,64K,…) and an app starts on a
sector boundary, so the candidates are `0x08008000`, `0x0800C000`, `0x08010000`.

## Disambiguating by disassembly (the decisive test)
For each candidate, compute the reset handler's file offset (`0x0801D251 - base`)
and disassemble. Only the correct base yields a sane reset handler. At
**`base = 0x08008000`** (reset at file offset `0x15250`):
```
ldr r0, [pc, #4]   ; literal -> 0x0801CF15
blx r0             ; call SystemInit
ldr r0, [pc, #4]   ; literal -> 0x0801D1E5
bx  r0             ; jump to _start
```
This is the canonical minimal Cortex-M reset handler, and **both literal pointers
(0x0801CF15, 0x0801D1E5) are odd (Thumb) and inside the image.** The other two
bases produced incoherent literal pools. Confirmed: **load address = 0x08008000.**

Cross-check: `0x0801CF15` (SystemInit) disassembles to
`ldr r1,=RCC; ldr r0,[r1]; orr r0,#1; str r0,[r1]` — i.e. set `RCC->CR` HSION bit.
That's exactly what STM32F4 `SystemInit` does. Independent confirmation.

## Resulting flash map (STM32F401RB, 128 KB)
```
0x08000000 ┌─────────────────────────────┐
           │ BOOTLOADER (32 KB)          │  not in our image; entered via Octave±
0x08008000 ├─────────────────────────────┤  <-- application load address
           │ APPLICATION (88 KB)         │  vector table, code, const data
0x0801D818 ├─────────────────────────────┤  end of image
           │ free / config (~9.5 KB)     │  (custom modes? settings?)
0x08020000 └─────────────────────────────┘  end of 128 KB flash

SRAM: 0x20000000 .. 0x2000FFFF (64 KB), initial SP = 0x2000FFF8
```

## Disassemble with the right base
```
arm-none-eabi-objdump -D -b binary -m armv7e-m -M force-thumb \
    --adjust-vma=0x08008000 firmware/launchkey-mini-mk3_v1.2-build461.syx.bin \
    > firmware/app_v1.2.thumb.asm
```
Caveat: a flat `objdump` of a raw binary can't tell code from data, so parts of the
listing will be nonsense (it disassembles constant pools and tables as if they were
instructions). For real structural analysis the next step is to load it into
**Ghidra** at base `0x08008000` as Cortex-M, which separates code/data and follows
the vector table. That's note 06.

## Why this matters for custom firmware
The app is a normal position-dependent image linked for `0x08008000`. To build our
own, the linker script's FLASH origin must be `0x08008000` (leaving the stock
bootloader intact at `0x08000000`), and the reset path must satisfy whatever the
bootloader checks before handing over (vector table at `0x08008000`, valid SP).
