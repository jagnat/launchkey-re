# Physical input path: control-surface scanner, MIDI input router, control-mapping layer

Confidence: ★=verified, ☆=strong inference, ?=guess.
The full input loop: ADC scan → condition → publish (`0x0800F_`), and USB-MIDI RX → router →
claim/route → `ctrl_in_*` transform stages → subscriber fan-out.

## Control-surface scanner (`0x0800F_` module) — the physical knob/strip/pad path
`control_surface_scan`@`0x0800B8B8` is a **polled task** (run from `peripheral_init_all`'s main
loop) that scans the analog controls, conditions each raw value (deadzone, calibration curve,
hysteresis), and publishes it.

**Control-id map ★★ HW-MEASURED 2026-07-03 (ctlscope v3)** — types from
`g_control_type_tbl`@`0x0801C7D0` (256 B, read via `control_type_get`@`0x08016792`):
| ids | type | what |
|---|---|---|
| `0x00-0x0F` | 3 | **the 16 pads**, reading order: top row l-r = 0x0-0x7, bottom = 0x8-0xF |
| `0x10-0x19` | 4 | buttons: 0x10 Scene Launch, 0x11 Stop/Solo/Mute, 0x12 Transpose, 0x13 Oct+, 0x14 Oct-, 0x15 Arp, 0x16 Fixed Chord, 0x17 Play, 0x18 Record, 0x19 Shift |
| `0x36,0x37` | 5 | touch strips: 0x36 pitch, 0x37 modulation |
| `0x38-0x3F` | 6 | **the 8 knobs**, l-r (NOT pots\|0x80 — that guess was wrong) |
| `0x50-0x58` | 7 | 9 entries, absent on the Mini — ☆ the 9 faders of the bigger Launchkey MK3s (family-shared scan config) |
| `0x78,0x79` | 8 | `control_surface_scan`'s special pair |
| `0x80-0x98` | 1/2 | **the 25 keybed keys**, one id per semitone (C=0x80 … C+2oct=0x98); type 1=white, 2=black (the 1/2 table pattern IS the keyboard layout) |
Keys and pad PRESSURE stream through the seam too (green-row readout tracked pad pressure)
— the publish seam sees the whole surface, notes included.

| symbol | addr | role | conf |
|---|---|---|---|
| `control_surface_scan` | `0x0800B8B8` | top scan task: runs the group scanners + handles ids 0x78/0x79 | ☆ |
| `control_raw_read` | `0x0800A9E0` | read raw 12-bit value + mode-nibble (`&0xf000`) for a control id, via `key_event_scan`, with low-16 hysteresis (11 callers) | ★ |
| `keybed_scan` | `0x0800F06A` | scan the **25 keybed keys** (emits `idx\|0x80` — the key ids, ex-"pot_scan"); ADC→value with deadzone (<0x259→0, mid linear, >0xdac→max) + `control_calib_lut` interpolation | ★ |
| `pitchstrip_scan` | `0x0800F4F0` | scan id **0x36** (pitch touch strip); center-scaled to 0x8000 (bipolar/pitchbend) | ☆ |
| `control_press_scan` | `0x0800EC54` | **the standalone press path** for pads/buttons/knobs/strips: iterate ids 0..0x7f, type∉{0,8}; mode-nibble 0 = digital threshold (raw≥0x800) → `control_value_emit(id, mapped-val)` + `emit_4`; mode 0x1000 = analog velocity/pressure state machine | ★ |
| `control_velocity_scan` | `0x0800F260` | strike/velocity scan for **type-6/7 controls (knobs/faders) in InControl mode ONLY** (`type∈{6,7} && raw&0xf000==0x2000`); 3 parallel state arrays (+0x180/+0x280/+0x380); emits press(id,0xffff)/pressure via `emit_4`/release. Publishes NOTHING at standalone | ★ |
| `control_value_emit` | `0x0800F840` | **publish** a conditioned (id,value) to subscriber callback list (`DAT_0800f8c0`) — 5 callers | ☆ |
| `control_value_release` | `0x0800F884` | publish a control release to subscriber list (`DAT_0800f8c8`) — 5 callers | ☆ |
| `control_calib_lut` | `0x0800F9C4` | per-control calibration/curve LUT lookup (used by `keybed_scan` interp) | ☆ |
**The publish seam, asm-decoded (2026-07-03):** `control_value_emit(r0=id, r1=value)` ★ —
walks subscriber table @`0x2000E3B0` (literal @`0x0800F8C0`): count byte at `+0`, callback
ptrs at `+4+i*4`, capacity 8 (☆ from the 0x24 stride to the next table); each called as
`cb(r0=id, r1=value)` via `blx r3` (arg shuffle in `FUN_0800f878` — decompiles empty, it's
`mov`-only). Three sibling fan-outs, same layout: `0x0800F85C`→table `0x2000E3D4`,
`control_value_release`@`0x0800F884`→`0x2000E3F8` (cb gets `r0=id` only),
`0x0800F8A2`→`0x2000E41C`. **This seam carries EVERY conditioned physical event with its
discrete id** ★★ HW-proven 2026-07-03: pads/buttons/knobs/strips via `control_press_scan`,
keys `|0x80` via `keybed_scan` — the full id map is the table above. It is the input backbone
for the custom page AND standalone knob→arp.
**Hook recipe:** prologue detour on `0x0800F840` (entry bytes `f8b50446` = push+`mov r4,r0`),
record/act on (r0,r1), replay the 2 displaced insns, resume `0x0800F844|1` — r2/r3 are dead
there. Implemented: `mods/asm/emit_tap.s` (ctlscope diagnostic). Alternatively REGISTER a real
subscriber: write our fn ptr into a free slot at `0x2000E3B0` from an init hook.
The 5 `control_claim_*` predicates gate which controls this module processes.
**Module still partly unmapped:** ~50 smaller `0x0800F_` helpers (state getters/setters,
`FUN_0800ff18`, the f9xx accessor cluster) remain `FUN_`.

## MIDI input router pipeline — `midi_in_router` backbone
`midi_in_router`@`0x0800C0C6` is the **per-tick input pipeline**, not a status-byte switch. It
resolves the source channel, walks that channel's route list, then runs the `ctrl_in_*`/note/
realtime stages in a fixed sequence (interleaved with two tiny `return;` barriers
`FUN_0800c166`/`c1f4`, left unnamed).
| symbol | addr | role | conf |
|---|---|---|---|
| `route_channel_get` | `0x08011198` | route/control id (<0x80) → byte; low nibble = MIDI channel (`DAT_080111b8`) | ☆ |
| `channel_route_list_get` | `0x080111AA` | channel (&0xf) → ptr to that channel's route-id list (0xff-terminated, `DAT_080111bc`) | ☆ |
| `control_claimed_any` | `0x0800B91C` | 1 if any of 5 feature maps claims this control id (router counts claimed controls per channel) | ☆ |
| `control_claim_u16/byte/id36/hi/id78` | `0x0800F4AE`/`F032`/`F67A`/`F212`/`F7C2` | the 5 leaf claim predicates (per-control u16 tbl / byte tbl / id==0x36 / id 0x80-0xff / id==0x78) — entry points into the `0x0800F_` feature module (68 funcs, mostly unmapped); claim tables `DAT_0800f4cc/f048/f690/f22c/f7d8` | ☆ |
| `midi_event_slot_get` | `0x0800BF60` | allocate a 16-entry event slot (`DAT_0800c370`), else fall back to `ctrl_cfg_get` | ☆ |
| `note_event_process` | `0x080119D6` | note-active/held-note update stage (tag 0x10000000; `note_active_*`, `held_note_scan`) | ☆ |
| `route_bit_test` | `0x080114C4` | inverted per-route bitmap test (`DAT_08011528`, 128 bits) | ☆ |
| `ctrl_feature_write` | `0x08011630` | commit a control value into the `0x0800F_` feature buffers (`DAT_0800fa80` u16 + `DAT_0800fa7c` dirty-bitmap) when cfg mode==1 | ☆ |
| `midi_in_publish_frame`/`_flush` | `0x08011688`/`0x0801166C` | two more subscriber fan-outs (lists @`0x08011700`/`0x080116fc`); with `midi_in_publish` (@`0x08011704`) = 3 adjacent callback-list slots = multi-phase publish | ☆ |

## Control-mapping layer (`0x08011xxx` `ctrl_in_*`) — input value transform
The value-transform stage between USB-MIDI RX and the feature subscribers. Each stage is invoked
per incoming control, looks up a **per-route descriptor** (`table[route]`), checks the active
tag (`word & 0xf0000000 == 0x10000000`), splits it into a **class byte** (`(word>>0x10)&0xff`)
+ **16-bit index** (`word & 0xffff`), reads/writes the value store via `midi_note_state_get/set`,
transforms the value, then `midi_in_publish`-es to all subscribers. `midi_in_publish`@0x080116A4
is a subscriber fan-out (callback array `_DAT_08011704`, count at `+0x20`). Chain driver
`FUN_0800c1b6` runs the `0xe3`/pickup/pot-press stages in sequence; `midi_in_router` runs
`ctrl_in_pot_release`.
| symbol | addr | role | conf |
|---|---|---|---|
| `ctrl_cfg_get` | `0x080111E2` | per-control 16-B config accessor (`_DAT_08011340 + route*0x10`); +2/+4=u16 lo/hi range, **+0xd&7 = mode** (0=fixed,1=relative,2=toggle,6=relative-clamp) | ★ |
| `ctrl_value_scale` | `0x08011538` | scale-about-base: `base ± ((|v-base|+1)*gain >> 16)` (16.16 fixed) | ☆ |
| `ctrl_value_scale_thunk` | `0x0801230C` | thin tail-call → `ctrl_value_scale` (relative decode) | ☆ |
| `ctrl_soft_pickup` | `0x0801159C` | **soft-takeover/pickup**: per-control last-value `DAT_08011624`[128]u16 + flags `DAT_08011628`[128]; returns 0 until physical control "catches" stored value | ☆ |
| `ctrl_pickup_gate` | `0x0801156E` | wraps `ctrl_soft_pickup` w/ 2-entry mode `DAT_0801162c`; clears flags | ☆ |
| `ctrl_route_enabled_a/b/c` | `0x08011B30`/`0x08011D10`/`0x08011E74` | per-route enable bitmaps (`DAT_08011d08`/`08011e6c`/`08012300`), 1 bit/route; a/b/c gate the wheel/special/pot stages resp. | ☆ |
| `route_is_incontrol` | `0x0800B8D2` | route<0x78 && route-mode `&0xf000==0x2000` → route is in InControl/DAW mode | ☆ |
| `ctrl_in_wheel` | `0x08011B46` | class 0xe0-0xe3 (pitchbend/wheel grp); `>>9` 14→7bit or note-state\|0x4000; gate=enable_a | ☆ |
| `ctrl_in_wheel_scaled` | `0x08011C7C` | class 0xe3; `ctrl_value_scale`+`ctrl_pickup_gate` then publish; gate=enable_a | ☆ |
| `ctrl_in_special` | `0x08011D26` | class 0xf6-0xf8 (realtime grp); passthrough + state; gate=enable_b | ☆ |
| `ctrl_in_special_pickup` | `0x08011DF2` | class 0xf7-0xf8; value `>>2` + `ctrl_soft_pickup`; gate=enable_b | ☆ |
| `ctrl_in_pot_modes` | `0x08011FE4` | class top-nibble 0x10-0x60; modes fixed/toggle/relative-clamp via cfg+0xd; gate=enable_c | ☆ |
| `ctrl_in_pot_release` | `0x080120A4` | same class; removes route from active list `DAT_08012304` (+0x34=count); mode-0 fixed; called by `midi_in_router` | ☆ |
| `ctrl_in_pot_press` | `0x0801215A` | same class; insert/evict in active list (find-min eviction); pitchbend-zone map (param thresholds 0x6000..0xe000); modes 1/2/4/5; gate=enable_c | ☆ |
**Routing note:** the `class`/route-id namespacing means a physical knob's value only reaches
the arp if its route descriptor maps it there — consistent with standalone knobs emitting raw
pot CCs not routed to `arp_cc_in_handler` (see arp.md "Knob → arp routing"). Class-byte →
physical-control decode (which class = which knob/fader/pad) is the open unknown here. The
class byte maps to a MIDI message type on output via `ctrl_out_encode` — see midi.md.
