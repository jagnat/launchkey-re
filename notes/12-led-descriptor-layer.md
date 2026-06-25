# 12 — LED descriptor layer & the route-B snag

## The colour pipeline (confirmed)
```
[session/MIDI logic] --writes--> descriptor[led].color_index (+0xf)
                                        │
   FUN_080141c2 (render) reads palette[ descriptor[led][0xf] & 0x7f ]
                                        │  palette @ 0x0801C250
                              FUN_0800bb36(led, rgb)  -> physical LED RGB buffer @ 0x2000AE40
                                        │
                              TIM1 ISR BCM matrix (notes 09/10)
```
- **Descriptor array**: `0x20003868`, 16 bytes/LED (`FUN_080111e2(led)=base+led*0x10`).
- **Descriptor fields**: `+0xc` mode (`&0xf` anim, `&0x30` source), `+0xd` blink/pulse,
  `+0xe` brightness/value, **`+0xf` = palette colour index** (`&0x7f`).
- `FUN_0801111e(desc)` clears `+0xc..+0xf` to 0 (LED off).

## The snag for surgical route B
A whole-firmware scan for byte-stores `strb _,[reg,#0xf]` found 9 sites — **none on
the descriptor array** (they hit unrelated structs with a `+0xf` field). So the
colour index is set via a **wide store** (likely a 32-bit write of `+0xc..+0xf`,
colour in the high byte) or by **copying a template**, not a lone `strb`. The
session-idle writer is therefore one or two abstraction hops further up and resists
the simple scans.

## Recommended sequencing (A confirms, then B)
1. **Route-A confirmation flash** (reversible, 3 bytes): set `palette[12]` → red,
   flash, observe. Proves whether index 12 is the session-idle colour.
2. With the index confirmed, **route B** = find the wide store / template that puts
   that index into a descriptor (search for the confirmed constant, e.g. `0xC`,
   moved then stored at descriptor `+0xc` as a word). Then patch only that.

## Patch locations
- Palette entry 12 (route A): file `0x14280`, bytes `2F AF FF 00` → e.g. `7F 00 00 00`.
- Route-B target: TBD (the descriptor colour write for the session pads).
