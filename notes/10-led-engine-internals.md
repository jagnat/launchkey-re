# 10 — LED engine internals & the path to the "session blue"

Goal driving this note: change the standalone **Session mode** idle colour (all pads
blue) to a red-ish colour. This requires finding where that blue is produced.

## What we've definitively mapped: the LED OUTPUT engine
The pads are an **8×16 multiplexed RGB matrix** driven by **binary-code modulation
(BCM)** for brightness, refreshed from the TIM1 ISR (note 09). Key addresses:

| Addr | Role |
|---|---|
| `0x2000DF70` | LED driver-A state struct |
| `0x2000DF08` | LED driver-B state struct |
| `0x2000BC4C` | per-column PWM compare framebuffer (8 × 0x40) |
| `0x40020418` | GPIOB_BSRR — column select |
| `0x40020810`(+8) | GPIOC_BSRR — row/anode select |

**Colour model (important):** `FUN_0800d8bc` loads **three words** from the driver
struct — `+4`, `+8`, `+0xc` — which are the **R / G / B bit-planes**: each is a
16-bit mask of *which pads* have that channel lit for the current BCM sub-frame.
So at the output layer:
```
all pads BLUE  =  B-plane bits = 0xFFFF , R-plane = 0 , G-plane = 0
all pads RED   =  R-plane bits = 0xFFFF , (small B for a warm/red-ish hue)
```
`FUN_0800d900` then packs the active planes into the GPIO/DMA output buffer, and
`FUN_0800d9d8` writes per-LED turn-off timestamps (the actual PWM). `FUN_0800d984`
just arms the driver. This whole layer is **colour-agnostic plumbing** — it renders
whatever planes it's handed.

## Why the "blue" isn't here (and where it must be)
The plane words `+4/+8/+0xc` are written through a **struct pointer held in a
register** (the render is *called with* `0x2000DF70`), so they leave no literal
cross-reference — that's why a base-address xref finds only the 3 driver functions.
The blue originates one or two hops **up**:
```
[Session mode logic]  ──sets──▶  [per-pad colour framebuffer]
        (idle ⇒ blue)                      │
                                           ▼ render (called w/ struct ptr)
                                  [R/G/B bit-planes @ 0x2000DF70+4/8/c]
                                           │
                                           ▼ TIM1 ISR drivers (MAPPED ✓)
                                     [8×16 BCM matrix]
```
We need: (a) the **per-pad colour framebuffer** and the **render** that turns it into
planes; (b) the **palette** (velocity→RGB) the DAW path uses; (c) the **Session-idle
writer** that fills the framebuffer with blue.

## Honest status & options to reach the blue
The output engine is fully understood. Reaching the exact blue constant needs ~2–4
more focused traces through the colour framebuffer + mode logic, and literal-xref
hits its limit there (struct-relative access). Two ways forward:

1. **Keep tracing statically** — find the render's caller (passes `0x2000DF70`),
   identify the colour framebuffer, then xref the Session-mode state to its idle
   fill. Most rigorous; a few more Ghidra hops.
2. **Anchor on the palette + empirics** — locate the velocity→RGB **palette table**
   in flash (a concrete artifact). The Session idle blue is almost certainly a known
   palette index; find that index's use. Faster to the goal; also tells us exactly
   which value = a nice muted red.

## Patch shape (once located) — feasibility: GOOD
Whatever we find, the change is tiny and data-only:
- If Session-idle writes a **palette index** (one byte) → change blue-index → red-index.
- If it writes an **RGB/plane constant** → change the constant.
Then re-encode (`xkey encode`) and flash via SysEx (recoverable; see note 08).
Risk is low because we're editing a colour value, not control flow or timing.
