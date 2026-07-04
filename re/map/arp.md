# Arp engine, rhythm/Euclid, arp page UI, knob routing

Confidence: ★=verified, ☆=strong inference, ?=guess.

## Engine core (`0x08013xxx` = UI/LED only; real step engine = `0x08014xxx`/`0x08017xxx`)
Clocked by MIDI `0xF8` (device free-runs 24 PPQN clock even at idle — see validation.md).
| symbol | addr | role |
|---|---|---|
| `g_arp_rate_divisors` | `0x08013B10` | `[3,2,6,4,12,8,24,16]` = 1/32..1/4 straight/triplet tick divisors (24 PPQN). ★★ HW-VERIFIED 2026-06-27: 1/16-straight = 6 clocks/step via `midi_capture.py arp` |
| `arp_apply_rate` | `0x080137FE` | `rate*2+(straight?0:1)` → divisor → program clock → refresh LEDs |
| `arp_rate_get`/`arp_triplet_get` | `0x080134C0`/`0x080134DE` | read rate index / triplet flag |
| `arp_step_emit` | `0x08014648` | per-step: consult rhythm; on HIT advance note ptr + emit (note-advance-on-hit is native = "Euclidean skip-step" semantics). Driven by `main_task_tick` step-timer (`g_arp_state_ptr+4` countdown) |
| `arp_held_note_add` | `0x08014448` | note-on → held-note list + re-`rhythm_decode` |
| `arp_is_enabled` | `0x080148B0` | true arp-on bool = `*g_arp_active_ptr` (byte@`0x2000e268`+0; 0 while merely holding Arp) |
| `held_note_update` | `0x08016A44` | maintain held-note linked list (`DAT_08016bf0`), arp input |
| `g_note_active_matrix_ptr` | `0x08016C00` | ☆ held-note set (arp input) |
| `transport_button_handler` | `0x080133D4` | Play → MIDI start/stop; known button ids 0x17/0x19/0x60/0x61/0x62 |
| `control_dispatch` | `0x0800C72C` | hub: routes control/button events to all feature handlers (22 callees) |
Sibling table `[2,4,6,8,8,32,6]`@`0x0801367E` = gate/swing?

## Rhythm engine (rest/step machinery) — where Euclid plugs in
| symbol | addr | role |
|---|---|---|
| `rhythm_rest_decide` | `0x0801760A` | **1=hit/0=rest**: `return mask >> (step & 0xff) & 1;` step ctr at state+0x10 wraps at period (state+8). Random uses LFSR (state+0). ★ |
| `rhythm_decode` | `0x080175B0` | `switch(config[+3])` → writes mask(state+4)/period(state+8). O=1/p1, OXO=5/p3, OXXO=9/p4, Random=flag, Deviate=`0x80-cfg[+9]`/p8. movs immediates (case2 body @`0x080175E2`). ★ **← our Euclid detour site** |
| rhythm pattern state | `0x20001fe8` | +0 random-flag, **+4 mask (u32)**, **+8 period**, +0xc LFSR, **+0x10 step ctr**, +0x14 last-cfg+3 |
| arp config struct | `0x20001fac` | +0 rate-div, +1 mode, +2 octave, **+3 Rhythm sel** (CC0x5b), +4 latch, +7 gate%, **+6 mutate**, **+9 deviate**, +0xa.. held-notes |
| CC arp-settings writer | `0x0801AAF0` | incoming CC **ch0 0xB0 on the DAW PORT** (not MIDI Port!) → arp config via `arp_cfg_apply`. Map: 0x55 Mode(sw 0-6→+1), 0x56 Rate(1-7→divisor,+0), 0x57 Octave(≤3,+1→+2), 0x58 Latch(+4), 0x59 Gate(0-99→`(v<<7)/99`,+7), 0x5a Mutate(clamp 0x22-0x5e,<<1,+6), 0x5b Rhythm(+3), 0x5d Deviate(+9) |
Inline patches only fit 8-bit masks (movs, period≤8); n=16 masks need movw → hence the
appended-code trampoline on `rhythm_decode`.

## Shipped Euclid mod (WORKING + HW-validated, standalone, 2026-07-01)
Engine: `mods/asm/rhythm_decode.s` detours `rhythm_decode` → appended `euclid_compute`
(reusable Thumb Bresenham sub). For cfg[3]∈5..10: **k = cfg[3]-1** (→ E(4..9, n)),
**n = 16-(cfg[9]>>3)** (cfg[9]=0 untouched → n=16), rot=0. Stock rhythms 0-4 byte-identical.
Controls (both HW-validated via `midi_capture.py arp`):
- **k = the Arp Rhythm PADS**: `arp-rhythm-guard-widen` (inline @`arp_rhythm_select` 0x0801387C)
  widens the pad-row guard 0..4→0..10 (drops the tbb identity-switch for `cmp #10 / strb r4`),
  so free pads **0xd/0xe/0xf → cfg[3]=5/6/7** = E(4/5/6, n).
- **n = the Deviate KNOB while the Arp button is HELD** (user guide p20): stock firmware writes
  cfg[9] from the held-Arp Deviate knob internally — no custom hook needed. Works in euclid
  rhythms (not gated to the Deviate rhythm). Verified: gaps sweep 24→18→12 as knob turns.
- DAW/host can also drive it: `cc5b-rhythm-clamp-0to10` widens `arp_cc_in_handler`'s 0x5b clamp
  1..4→1..10 (inline @0x12C1C) so DAW-port CC selects euclid 5-10 (our validation channel).
Measured gap-value sets matched `euclid_ref.py` exactly (k4=24×4, k5=24/18, k6=18/12, k7=18/12,
k9=12/6, k11=12/6) → on-device math proven.
Caveats: cfg[9] (Deviate) **double-duties as a timing/swing param** (clean {4,8} gap artifact) —
a side-effect-free home for n is still wanted. Next planned: Mutate knob → rotation (rot).

## Knob → arp routing (final truth after two wrong verdicts)
- **Held-Arp routing (the answer):** while the Arp button is physically HELD the knobs route
  INTERNALLY to arp cfg (Tempo/Swing/Gate/Mutate→cfg[6]/Deviate→cfg[9]; no CC emitted). This is
  the shipped n-control. Every earlier "knobs are dead" test turned knobs WITHOUT holding Arp.
- **Not held:** knobs emit only generic pot CCs **0x15..0x1c on ch16 (0xBF), DAW port**
  (rightmost 3 = 0x1A/0x1B/0x1C). These do NOT reach `arp_cc_in_handler` (only ch0 0x55-0x5d on
  the DAW port do). The "knobs do Mutate/Deviate in Ableton" behavior = Ableton's Launchkey
  script bridging, not firmware routing. DAW-mode enable `9F 0C 7F` does not change this.
- **Buildable alternative:** the pots ARE scanned+published internally via
  `control_value_emit`@`0x0800F840` → subscriber list `DAT_0800f8c0` (see input.md). The arp
  simply isn't on that list; a standalone knob→arp mod = add a subscriber that writes arp cfg.

## Arp Controls PAGE UI (note 23) — fully traced press→config
Two structs: UI state `g_arp_state_ptr`@`0x2000e628` (+0 panel-active, +2 held, **+0xc active
group 0-3**) vs arp config@`0x20001fac` (engine reads it). The `0x08013xxx` cluster never writes
config — it calls a bridge in the engine cluster. **4 groups** (`DAT_08013b00` = 4-entry colour
table): 0=Mode(purple,7cells `arp_type_select`), 1=Rate(orange `arp_rate_select`),
2=Octave(blue,5 `arp_octave_select`), **3=Rhythm(yellow,5cells pads8-0xc `arp_rhythm_select`)**.
Each value handler = fetch pressed value (`arp_value_fetch`→`arp_cfg_snapshot`) → switch
range-guard → apply (`arp_value_apply`→**`arp_cfg_apply`**). `arp_cfg_apply` writes config
(`arp_cfg_copy`) then calls `rhythm_decode` — i.e. the apply terminates in our Euclid detour.
CC 0x5b path (`arp_cc_in_handler`) shares the same `arp_cfg_apply`. Render: `arp_page_render`
@`0x08013508` Rhythm branch paints only pads 8-0xc (`DAT_08013aec` dim / `DAT_08013af0` active);
**pads 0xd/0xe/0xf are FREE** (now used by the euclid mod).
| symbol | addr | role |
|---|---|---|
| `arp_control_handler` | `0x0801391C` | arp page input router. top row 0-3=group select→state+0xc; bottom 8-0xf=value→per-group handler |
| `arp_page_render` | `0x08013508` | light 16 pads for the arp page (`DAT_08013b00`=4 group colours) |
| `arp_mode_select` | `0x08013B34` | **NOT the arp page** — drives sibling struct (`DAT_08013e00`=`0x2000e648`), likely scale/fixed-chord page (unconfirmed) |

## Input-side findings for a custom toggle (2026-07-03: pads = ids 0x00-0x0F)
Goal: a deliberate pad/button to toggle the custom page.
- **Pads are control ids `0x00-0x0F`** (type 3 in `g_control_type_tbl`@`0x0801C7D0` — see
  input.md), published at standalone by `control_press_scan` via
  `control_value_emit(id, value)`@`0x0800F840`. Consistent with `arp_control_handler`'s
  switch semantics (top row 0-3 = group, bottom 8-0xf = value) reading param_1 AS the pad id.
- The v1/v2 scope verdicts ("param_1 ≠ pad id, id travels in r4") were an ARTIFACT: both
  scopes stored to `0x2000DD37`, which lives inside firmware statics and gets overwritten
  with `id&8`-like values every scan (post-mortem in leds.md). ctlscope v3 (debug pair moved
  to free RAM `0x2000F000`, id+value rendered on bottom/top pad rows) is the clean re-test.
- Known BUTTON ids (0x17/0x19/0x60/0x61/0x62, type 4) remain a fallback toggle; UART printf
  (`usart_init`@`0x08009CB0`) is not needed.

## Design direction (2026-06-28 pivot, user: "go bolder / replace stock")
Parametric **"tracks × generator primitive × focus UI"** model: a Euclidean rhythm and an arp
direction are the SAME op — distribute k events over n slots (Bresenham). One primitive
`euclid_compute(k,n,rot)` drives every axis: Time(rhythm), Pitch(note order), Octave(+
Turing/stochastic variant), Accent. UI sketch: top row = TRACK focus, 3 knobs = (k,n,rot) for
the focused track, bottom row = LIVE pattern view (lit=hit). Stock {7 modes × 5 rhythms × 4 oct
× mutate × deviate} = projections of this.
