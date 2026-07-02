# Firmware map — curated cheat-sheet (read this at session start)

## Current status (Claude init — read first, keep updated each milestone)
**Project goal:** PRIMARY = targeted firmware mods (LED/arp/scale/velocity), don't break
things (reversible, validate no-flash first, never flash without go-ahead). ANCILLARY =
full semantic map — grow coverage when convenient, never at the device's/mod's expense.
**Last checkpoint (2026-07-01):** **On-device Euclidean arp control — WORKING + HW-validated,
STANDALONE (no DAW).** Both control surfaces drive the euclid engine (`mods/asm/rhythm_decode.s`,
rhythm_decode detour @0x080175B0 → appended `euclid_compute`), for cfg[3]∈5..10:
- **k (density) = the Arp Rhythm PADS.** `arp-rhythm-guard-widen` (inline @`arp_rhythm_select`
  0x0801387C) widens the pad-row guard 0..4→0..10 (drops the tbb identity-switch for a direct
  `cmp #10 / strb r4`), so free pads **0xd/0xe/0xf → cfg[3]=5/6/7**. Engine: **k = cfg[3]-1** →
  E(4/5/6, n).
- **n (length) = the Deviate KNOB.** Engine: **n = 16-(cfg[9]>>3)**. Stock firmware already
  writes cfg[9] from the Deviate knob **while the Arp button is HELD** (user guide p20) — this
  is the routing note 25 MISSED (it tested knobs WITHOUT holding Arp). cfg[9]=0 (untouched)→n=16
  so pads alone still give E(k,16) unchanged. Verified NOT gated to Deviate rhythm (works in euclid).
Keeper mods (`mods/build.py`): `led-palette-42-red`, `cc5b-rhythm-clamp-0to10` (CC 0x5b 1..4→1..10),
`euclid-rhythm-engine`, `arp-rhythm-guard-widen`. Validated via `midi_capture.py arp`: pads →
E(4/5/6,16); held-Arp Deviate knob sweeps n (gaps 24→18→12...). **⚠ The "knob dead-end" verdict
below (2026-06-28) is WRONG/superseded — knobs DO route to arp params, gated on Arp-held.**
Next: Mutate knob → rotation (rot), 3rd param. **Coverage:** 328/1233 funcs (26.6%).
**OPEN FORK (pick next):** A=accept DAW-CC v1 / **C=pivot control to PADS (standalone, we own
arp_control_handler/arp_rhythm_select) + live pattern view** / D=~~RE the pot ADC-scan→CC-emit
path~~ **DONE (go-nuts-6): found it — `control_surface_scan`/`pot_scan`/`control_value_emit`
(see "Control-surface scanner"). Knob→arp is now buildable: add a subscriber to
`control_value_emit`'s list (`DAT_0800f8c0`) that writes arp cfg.** n needs a side-effect-free
home (not cfg[9]).
**ARCHITECTURE PIVOT (2026-06-28):** dropped the fixed-preset picker for a **parametric
"tracks × generator primitive × focus UI"** model (user direction, "go bolder / replace
stock"). Core insight: a Euclidean rhythm and an arp direction are the SAME op — distribute
k events over n slots (Bresenham). So one primitive `euclid_compute(k,n,rot)` drives every
axis: Time(rhythm), Pitch(note order), Octave(+ Turing/stochastic variant), Accent. UI:
top row = TRACK focus, 3 knobs = (k,n,rot) for the focused track, bottom row = LIVE pattern
view (lit=hit). Stock {7 modes × 5 rhythms × 4 oct × mutate × deviate} = projections of this.
**Active task:** Time-track slice. **TRACER COMPLETE + HW-VALIDATED (2026-06-28):**
`mods/asm/rhythm_decode.s` computes Euclidean masks LIVE via `euclid_compute` (reusable
Thumb sub @ appended `0x0801D8AC`, 232 B). cfg[3] 5..10 → k={4,5,6,7,9,11}, n=16, rot=0.
Flashed `firmware.bin`(88320B, +232) — all 6 presets measured via DAW-port CC 0x5b sweep,
gap-value sets matched `euclid_ref.py` exactly (k4=24×4, k5=24/18, k6=18/12, k7=18/12,
k9=12/6, k11=12/6 — discriminating values all correct → on-device math proven). Stock 0..4
byte-identical. **CC channel learned: arp CC handler listens on the DAW PORT, not MIDI Port**
(earlier "inconclusive" was wrong port). New keeper mod `cc5b-rhythm-clamp-0to10` widens the
arp_cc_in_handler 0x5b clamp 1..4→1..10 (replaces a tbb identity-switch; inline @0x12C1C) so
DAW MIDI selects euclid 5-10. cfg-derived k is the seam where knobs attach next.
**KNOB CCs captured (2026-06-28):** the 8 arp pots send generic pot CCs **0x15..0x1c on
ch16 (0xBF)** on the DAW port (rightmost 3 = 0x1A,0x1B,0x1C). **These do NOT reach the arp
CC writer arp_cc_in_handler** (tested: pot 0x1b/ch16 did not change rhythm; only 0x55-0x5d/ch0
do). So physical-knob→arp-param routing is a SEPARATE path, likely gated on the Arp page
being held. Wiring knobs to (k,n,rot) needs either: (a) a flash-experiment hooking
arp_cc_in_handler's mutate(0x5a)→k to test if the physical knob drives it internally, or (b) RE
of the pot-CC handler (find who consumes 0x15-0x1c/ch16 → arp). Open decision.
**KNOB-WIRING FLASH-EXPERIMENT DONE (2026-06-28) — verdict:** engine now reads k=cfg[6]
(Mutate), n=cfg[9] (Deviate) when cfg[3]∈5..10 (parametric euclid). **Host/DAW CC drives it
perfectly** (sent ch0 0x5a/0x5d/0x5b on DAW port: Mutate flips density 12s↔6s, Deviate
changes pattern → k & n live, engine reads config correctly). **BUT physical knobs do NOT
write cfg[6]/cfg[9]** — tested latched, arp-page-held, all-8-knobs swept, and a
crank-then-force-recompute test: zero effect. Standalone the knobs emit only raw pot CCs
(0x1a-0x1c/ch16); the device does not internally route them to the arp. **Hypothesis: needs
Novation InControl/DAW-mode handshake (host/Ableton) to activate knob→arp routing** (matches
user seeing Mutate/Deviate work "in Ableton"). Also **cfg[9]=Deviate double-duties as a
timing/swing param** (clean {4,8} gap artifact) → bad home for n; n needs a side-effect-free
field. **Net: Time track = DAW/host-CC-playable today; physical-knob binding is unsolved.**
**❌ CORRECTION (2026-07-01): the above knob dead-end is WRONG.** The knobs DO route to arp
params — but ONLY while the **Arp button is physically HELD** (user guide p20: held-Arp knobs =
Tempo/Swing/Gate/Mutate/Deviate). Every "zero effect" test above turned knobs without holding
Arp, so they emitted generic pot CCs (0x15-0x1c/ch16) instead of routing to cfg. With Arp held
the Deviate knob writes cfg[9] and the Mutate knob writes cfg[6] internally (no CC emitted, and
NOT gated to Deviate rhythm — verified in euclid rhythm). This is now the shipped n-control. See
notes/34 + the "Last checkpoint" at top.
**COVERAGE (2026-06-28):** mapped the **control-mapping / input-transform layer** (the
`0x08011xxx` `ctrl_in_*` family) — see "Control-mapping layer" below — then the
**scale/chord engine** (`0x08016xxx` + editor @`0x0801ACF0`) — see "Scale / Chord engine".
then the **MIDI output / TX stack** (`midi_tx`/`ctrl_out_encode`/`midi_tx_sysex`) — see
"MIDI output / TX stack". Now 197/1233 funcs (16.0%), 28.1% code bytes. These are the
musical-engine I/O path; the control layer is where knob min/max/soft-takeover/relative modes
live (knob-routing), and `ctrl_out_encode` is the symmetric encoder that closes note 26's
open "class byte → MIDI type" question — then the **control-smoothing/thinning engine**
(`ctrl_smooth_emit` + `ctrl_track_*`, see that section). Then a **low-hanging-fruit bulk pass**
(`scripts/classify_stubs.py`): +29 `j_<callee>` forwarder thunks + 45 `nullsub_<addr>` empty
(`bx lr`) functions, auto-classified from decompiled bodies. **Now 284/1233 funcs (23.0%),
29.5% bytes** — function% jumped, bytes flat (these are all tiny). Re-run `classify_stubs.py`
after future naming milestones: more thunks become classifiable as their targets get named.
**COVERAGE (go-nuts-5):** mapped the **MIDI input router pipeline** (`midi_in_router` backbone
+ `control_claim_*` predicates) — see "MIDI input router pipeline". This closes the input loop:
router → claim/route → the `ctrl_in_*` stages (note 26).
**PERIPHERAL SWEEP (go-nuts-5):** audited every MMIO peripheral (via `PTR_<REG>` usage) and
closed the gaps — **every STM32F401 peripheral the firmware uses now has a named driver**
(added USART/CRC/EXTI/I2C drivers, clock/flash/pwr bringup, RCC enable+clk-freq helpers, GPIO
config primitive). See expanded "Hardware drivers".
**COVERAGE (go-nuts-6):** mapped the **control-surface scanner** (`0x0800F_` module) — the
physical pot/strip/pad ADC-scan→condition→emit path (the missing piece from note 25's knob
investigation). See "Control-surface scanner". Now 328/1233 funcs (26.6%), **35.0% bytes**.
**Next steps (open decision):**
- (A) Accept host/DAW-CC as v1 control surface; move on (pad-render live view / Pitch-Octave RE).
- (B) ~~InControl test~~ DONE 2026-06-28: sent DAW-mode enable `9F 0C 7F` (DAW port) + twisted
  Mutate → STILL no effect. Conclusion: **knobs are OUTPUT-ONLY standalone** — firmware sends
  knob CCs out, doesn't route them to the arp internally; the "knobs do Mutate/Deviate"
  behavior is **Ableton's Launchkey script bridging**, not firmware. Standalone knob→arp would
  have to be BUILT by hooking the internal knob ADC-scan/CC-emit path (deeper, separate RE).
- (C) Pivot control surface to the PADS (we fully own arp_control_handler/arp_rhythm_select) —
  e.g. k/n via pad presses, no knob dependency.
- Pick a side-effect-free home for n (not cfg[9]); find/allocate a spare cfg or RAM byte.
**Device note:** arp note-ons appear on **MIDI Port ch0** only when actually streaming;
use **Latch** + a held chord so it free-runs for capture. Tracer fw currently on device
(OXXO = E(3,8)); reflash stock or stage-2 to restore.
**Housekeeping:** `CLAUDE.md` + `re/MAP.md` not yet committed to git. SWD ruled out
(no external test points; user won't open unit).
**CANONICAL BUILD = `mods/build.py`** (accumulating mod pipeline — single source of truth,
see note 22). Stacks all mods onto `stock.bin` → `build/firmware.bin` + `build/firmware.syx`.
Mod kinds: `inline` (offset+bytes, asserts stock `frm`) / `append` (asm in `mods/asm/`,
auto-allocated flash-tail addr + `b.w` detour). Toolchain: arm-none-eabi-* under
/Applications/ArmGNUToolchain. Encode verified bit-identical to orig.syx. Flash:
`.venv/bin/python scripts/flash.py build/firmware.syx --go` + Scene Launch. `.venv` has mido.
Current manifest: `led-palette-42-red` (idx42→red) + `euclid-rhythm-engine` (stock 0-4 kept
byte-identical + euclid 5-10 dormant). **Strategy shift:** go deeper on the UI to *replace*
stock behaviours, not just extend — next is documenting arp-page UI (render 0x08013508 /
input 0x08013B34) then a UI mod to reach rhythm selectors 5-10.

---

**Naming convention:** semantic names (e.g. `arp_step`, `note_active_get`) are
identified roles. Names like `arp_3004` / `scale_6c8` / `midi_listener_1b46` are
**module-prefixed placeholders** — the function is confirmed to live in that module
(verified address range), but its precise role is not yet read. Upgrade these as read.
Two auto-classified prefixes (from `scripts/classify_stubs.py`): **`j_<fn>`** = a tiny
forwarder/veneer that tail-calls `<fn>`; **`nullsub_<addr>`** = a provably-empty (`bx lr`)
function. These are mechanical, not deeply read — but accurate.


Dense, high-confidence facts so we don't re-derive. Confidence: ★=verified,
☆=strong inference, ?=guess. Update when `symbols.tsv` grows.

## Memory
| region | addr | notes |
|---|---|---|
| App load base | `0x08008000` | ★ image = 88,088 B, ends ~`0x0801D818` |
| Flash data/const | ~`0x0801A000`+ | ★ palette, velocity curves, tables live here |
| SRAM | `0x20000000`–`0x2000FFFF` | ★ 64 KB; init SP `0x2000FFF8` |

## Named symbols (also in symbols.tsv)
| addr | name | conf | what |
|---|---|---|---|
| `0x080095A8` | `led_key_matrix_scan_isr` | ★ | TIM1-ISR 8×16 BCM matrix scan (notes 9–10) |
| `0x080141C2` | `led_render_resolve_palette` | ★ | descriptor idx → palette RGB → rgb buffer |
| `0x08012608` | `velocity_curve_apply` | ★ | installs curve `g_velocity_curves[idx]` (note 18) |
| `0x080126FC` | `velocity_curve_set` | ★ | clamp ≤3, store `g_settings+2`, re-apply, light LED |
| `0x0801267C` | `settings_apply_all` | ☆ | re-applies many `g_settings` fields on mode restore |
| `0x0801CF14` | `SystemInit` | ★ | RCC HSION etc. |
| `0x0801D1E4` | `app_start` | ★ | C runtime entry |
| `0x0801D250` | `Reset_Handler` | ★ | vector[1] |
| `0x0801C250` | `g_color_palette` | ★ | 128×4 B, **B,G,R,pad** (note 16) |
| `0x0801A158` | `g_velocity_curves` | ★ | 3 sets × 2 ch × 128 B, ends `0x0801A458` (note 18) |
| `0x080127F0` | `g_settings_subtable_127f0` | ☆ | 3×u16 `{0,0x5555,0xaaaa}`, indexed by `g_settings+4` |
| `0x20002128` | `g_settings` | ★ | RAM device-settings struct (see below) |
| `0x20003868` | `g_led_descriptors` | ★ | 16 B each; `+0x0f` = palette index (notes 12/16) |
| `0x2000AE40` | `g_led_rgb_buffer` | ★ | physical per-LED RGB the ISR shifts out |

**Hardware drivers (SVD-proven, see `hardware.md`):** `peripheral_init_all`@080083BC,
`timers_init_all`@08009D94, `systemclock_config`@0800DBD4, `key_columns_read`@0800D9D8
(GPIOC_IDR), `matrix_row_drive`@0800D8BC (GPIOB_BSRR), `matrix_pin_reconfig`@080093EA,
`key_event_scan`@08009878, `key_debounce`@0800DA4C, `adc_dma_driver`@0800D900 (touch
strips), `spi1_dma_driver`@0800953E. Registers labeled in `firmware.c` via `LoadSvd.java`
+ `ApplyMmioPointers.java` as `PTR_<REG>_<addr>` literals (grep those, not `q.py reg`).

**Peripheral coverage = complete (2026-06-28).** Audited via `PTR_<REG>` usage; every MMIO
peripheral now has ≥1 named driver. Added drivers:
| peripheral | driver(s) | role |
|---|---|---|
| Clock/Flash/PWR | `clock_config_boot`@08008DC2, `flash_cache_enable`@08009398, `rcc_hclk_from`@0800DBF0, `rcc_pclk1_from`@0800DBFC, `rcc_pclk2_from`@0800DC0C | HSE+PLL+flash-latency+voltage-scale bringup; flash I/D-cache; HCLK/PCLK1/PCLK2 freq from RCC_CFGR prescalers |
| RCC enables | `rcc_ahb1_enable`@0800833C, `rcc_apb1_enable`@08008342, `rcc_apb2_enable`@0800835A, `rcc_ahb1_enable2`@080093C4, `rcc_pwr_clk_enable`@0800D870 | `RCC_xxxENR \|= mask` clock-gate shims |
| GPIO | `gpio_pin_config`@0800999C | per-pin MODER/OTYPER/etc config primitive (6 callers) |
| USART1/2/6 | `usart_init`@08009CB0 | configures CR1/CR2/CR3 + baud for the 3 UARTs |
| I2C1 | `i2c_xfer`@0800D024 (xfer state machine), `i2c1_init`@08008E6C (clocks+pins) | the real I2C driver (was only incidentally touched) |
| CRC | `crc_compute`@0801895C, `crc_update_byte`@08018944 | CRC32 unit (enable, feed words BE, bitwise byte step) |
| EXTI | `exti_config`@08009A7C | EXTI IMR/EMR mask + edge-mode config |
| USB GPIO | `usb_gpio_init`@0801586E, `usb_otg_gpio_init`@08015864 | PA11/PA12 + OTG_FS pin/PHY setup |
Remaining unnamed MMIO-touchers are tiny redundant veneers (GPIO config thunks `FUN_08008d4e/d50`
— Ghidra phantoms that won't take a name) — no whole peripheral is unmapped.

## `g_settings` @ 0x20002128 (the thread into musical features)
Pointer used in code as `DAT_080127d8`. Known fields (offset from base):
| off | meaning | conf |
|---|---|---|
| `+0` | velocity curve index, set A (0–2 curve, 3=fixed) | ☆ |
| `+2` | velocity curve index, set B — written by `velocity_curve_set` | ★ |
| `+1,+3,+4,+5,+6,+0x0e` | read by `settings_apply_all` → other mode toggles/selectors | ? |
| `+4` | indexes `g_settings_subtable_127f0` (<3) | ☆ |
→ **Next:** decode the remaining fields by reading each `settings_apply_all` callee.

## Vector table / ISRs (scripts/scan_vectors.py)
All exception + SVD-named IRQ handlers named in `symbols.tsv`. Cross-checks:
- **TIM1_UP_TIM10_IRQHandler == `led_key_matrix_scan_isr`@080095A8** (the matrix scan
  runs off TIM1) — independent confirmation of the LED/key engine.
- **TIM2_IRQHandler**@08008378 = a real ISR (candidate **arp/tempo clock** — check when
  chasing the arp engine).
- **OTG_FS_IRQHandler → `usb_otg_fs_isr`@08018184** (1298 B, 24 callees) — USB **is**
  interrupt-driven (earlier "polled" guess was wrong). USB device stack spans ~0x08015800
  -0x08019xxx (physically interleaved with the `confstore`/`extdata` .c ranges).
- Most other IRQ vectors point to weak default stubs in the `0x0801D2xx` cluster (unused
  peripherals).
- `assert_failed`@0800DC6C = the `__FILE__`/line assert sink.
Regenerate/extend with `scripts/scan_vectors.py`.

## USB-MIDI RX path (note 19) — the musical-engine gateway
Source modules (from kept `__FILE__` strings): `inputmidi_listener.c`@0x08011xxx,
`midiobj_backend.c`@0x08014xxx. USB ports: MIDI Port / DAW Port / "MIDI Int" (InControl).
| symbol | addr | role |
|---|---|---|
| `midi_in_router` | `0x0800C0C6` | ★ parse+dispatch incoming MIDI → 12 type handlers (17 callees) |
| `midi_in_publish` | `0x080116A4` | ★ fan-out event to listeners (all 12 handlers call it) |
| `midi_note_state_get`/`set` | `0x0800CDCC`/`0x0800CDF8` | ★ read/write MIDI note state (27 callers) |
| `g_midi_note_value_ptr` | `0x0801531C` | ★ 16ch×128×2B 14-bit value table (`&0x3fff`) |
| `g_midi_note_state_ptr` | `0x08015320` | ★ 16ch×128×1B note on/off+vel |
| `g_note_active_matrix_ptr` | `0x08016C00` | ☆ held-note set (arp input), engine 0x08016xxx |
| 12 handlers | `FUN_0801179c…0801215a` | ? one per message type (note-on/off/CC/pitchbend) — not yet split |
| `FUN_0800C238`/`C2D6` | — | ☆ the two input feeds (USB vs DAW) |
| MIDI-out builders | `midi_out_forward`@0801bbec, `chord_edit_handler`@0801acf0, `ctrl_out_encode`@08017940 | ☆ now named — see "MIDI output / TX stack" |

## Control-surface scanner (2026-06-28, coverage) — `0x0800F_` module = the knob/strip path
**This is the physical-input ADC→value path note 25 wanted.** `control_surface_scan`@`0x0800B8B8`
is a **polled task** (run from `peripheral_init_all`'s main loop) that scans the analog controls,
conditions each raw value (deadzone, calibration curve, hysteresis), and **publishes** it.
| symbol | addr | role | conf |
|---|---|---|---|
| `control_surface_scan` | `0x0800B8B8` | top scan task: runs the 3 group scanners + handles ids 0x78/0x79 | ☆ |
| `control_raw_read` | `0x0800A9E0` | read raw 12-bit value + mode-nibble (`&0xf000`) for a control id, via `key_event_scan`, with low-16 hysteresis (11 callers) | ★ |
| `pot_scan` | `0x0800F06A` | scan the **8 pots** (ids 0x80+); ADC→value with deadzone (<0x259→0, mid linear, >0xdac→max) + `control_calib_lut` interpolation | ☆ |
| `pitchstrip_scan` | `0x0800F4F0` | scan id **0x36** (pitch touch strip); center-scaled to 0x8000 (bipolar/pitchbend) | ☆ |
| `control_velocity_scan` | `0x0800F260` | scan low ids (0+) with strike/velocity detection (pads/keys); 3 parallel state arrays (+0x80/+0x180/+0x280) | ☆ |
| `control_value_emit` | `0x0800F840` | **publish** a conditioned (id,value) to a subscriber callback list (`DAT_0800f8c0`) — 5 callers | ☆ |
| `control_value_release` | `0x0800F884` | publish a control release to subscriber list (`DAT_0800f8c8`) — 5 callers | ☆ |
| `control_calib_lut` | `0x0800F9C4` | per-control calibration/curve LUT lookup (used by `pot_scan` interp) | ☆ |
**Knob→arp seam (updated):** the pots ARE scanned and published internally via
`control_value_emit` → its subscriber list. Note 25's "knobs are output-only" really means **the
arp is not on that subscriber list** (the published value goes to the USB-CC-out path / Ableton
bridge, not to `arp_cfg_apply`). A standalone knob→arp mod would hook here: add a subscriber to
`control_value_emit`'s list (`DAT_0800f8c0`) that writes arp config, or have it target the arp's
(class,index). The 5 `control_claim_*` predicates gate which controls this module processes.
**Module still partly unmapped:** ~50 smaller `0x0800F_` helpers (state getters/setters,
`FUN_0800ff18`, the f9xx accessor cluster) remain `FUN_`.

## MIDI input router pipeline (2026-06-28, coverage) — `midi_in_router` backbone
`midi_in_router`@`0x0800C0C6` is the **per-tick input pipeline**, not a status-byte switch. It
resolves the source channel, walks that channel's route list, then runs the `ctrl_in_*`/note/
realtime stages (note 26) in a fixed sequence (interleaved with two tiny `return;` barriers
`FUN_0800c166`/`c1f4`, left unnamed). Newly named:
| symbol | addr | role | conf |
|---|---|---|---|
| `route_channel_get` | `0x08011198` | route/control id (<0x80) → byte; low nibble = MIDI channel (`DAT_080111b8`) | ☆ |
| `channel_route_list_get` | `0x080111AA` | channel (&0xf) → pointer to that channel's route-id list (0xff-terminated, `DAT_080111bc`) | ☆ |
| `control_claimed_any` | `0x0800B91C` | 1 if any of 5 feature maps claims this control id (router counts claimed controls per channel) | ☆ |
| `control_claim_u16/byte/id36/hi/id78` | `0x0800F4AE`/`F032`/`F67A`/`F212`/`F7C2` | the 5 leaf claim predicates (per-control u16 tbl / byte tbl / id==0x36 / id 0x80-0xff / id==0x78) — entry points into the `0x0800F_` feature module (68 funcs, still mostly unmapped) | ☆ |
| `midi_event_slot_get` | `0x0800BF60` | allocate a 16-entry event slot (`DAT_0800c370`), else fall back to `ctrl_cfg_get` | ☆ |
| `note_event_process` | `0x080119D6` | note-active/held-note update stage (tag 0x10000000; `note_active_*`, `held_note_scan`) | ☆ |
| `route_bit_test` | `0x080114C4` | inverted per-route bitmap test (`DAT_08011528`, 128 bits) | ☆ |
| `ctrl_feature_write` | `0x08011630` | commit a control value into the `0x0800F_` feature buffers (`DAT_0800fa80` u16 + `DAT_0800fa7c` dirty-bitmap) when cfg mode==1 | ☆ |
| `midi_in_publish_frame`/`_flush` | `0x08011688`/`0x0801166C` | two more subscriber fan-outs (lists @`0x08011700`/`0x080116fc`); with `midi_in_publish` (@`0x08011704`) these are 3 adjacent callback-list slots = a multi-phase publish | ☆ |
**Next lead:** the `0x0800F_` feature module (68 funcs) — the `control_claim_*` predicates and
`ctrl_feature_write` are its entry points; the 5 claim tables (`DAT_0800f4cc/f048/f690/f22c/f7d8`)
distinguish its sub-features.

## Control-mapping layer — input value transform (2026-06-28, coverage)
The `0x08011xxx` `ctrl_in_*` family is the **value-transform stage** sitting between USB-MIDI
RX and the feature subscribers. Each stage is invoked per incoming control, looks up a
**per-route descriptor** in a table indexed by route-id (`table[route]`), checks the active
tag (`word & 0xf0000000 == 0x10000000`), splits it into a **class byte** (`(word>>0x10)&0xff`)
+ **16-bit index** (`word & 0xffff`), reads/writes the value store via `midi_note_state_get/set`,
transforms the value, then `midi_in_publish`-es to all subscribers. `midi_in_publish`@0x080116A4
is a **subscriber fan-out**: iterates a callback array (`_DAT_08011704`, count at `+0x20`).
Chain driver `FUN_0800c1b6` runs the `0xe3`/pickup/pot-press stages in sequence; `midi_in_router`
runs `ctrl_in_pot_release`.
| symbol | addr | role | conf |
|---|---|---|---|
| `ctrl_cfg_get` | `0x080111E2` | per-control 16-B config accessor (`_DAT_08011340 + route*0x10`); fields +2/+4=u16 lo/hi range, **+0xd&7 = mode** (0=fixed,1=relative,2=toggle,6=relative-clamp) | ★ |
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
**Knob-routing note:** this layer transforms & republishes control values but the `class`
byte / route-id namespacing means a physical knob's value only reaches the arp if its route
descriptor maps it there — consistent with the earlier finding that standalone knobs emit raw
pot CCs (0x1a-0x1c/ch16) that aren't routed to `arp_cc_in_handler`. Class-byte → physical-control
decode (which class = which knob/fader/pad) is the next unknown if pursuing knob→arp wiring.

## Scale / Chord engine (2026-06-28, coverage) — `0x08016xxx` + editor `0x0801ACF0`
Strings confirm the feature ("Scale On/Set", "Scale Chord", "Fixed Chord", "User Chord",
"Chord Pickup"). **Three observable-config objects**, each an "observer pattern" struct
(callback array + count; mutators notify all observers on change), one per `.c` module:
| module / obj | file | obj-ptr | API | notes |
|---|---|---|---|---|
| **layout_channel** | `layout_channel.c` | `g_layout_cfg_ptr`@`0x08016974` | `layout_observer_add`@6908, `layout_channel_set`@692C (3 ch bytes, nibble), `layout_mode_get`@695C | per-zone MIDI channel/mode (3 entries, `&0xf`); observers @+4, count @+0x24 |
| **scale** | `scale.c` | `g_scale_cfg_ptr`@`0x080169DC` | `scale_observer_add`@698C, `scale_setting_get`@69B0 (+0x10 ?), **`scale_quantize_note`@69B6**, `scale_def_lookup`@69E8 | obj: +0 enable, +4..+0xf = 12-entry interval map, observers @+0x14, count @+0x34 |
| **chord/scale-set** | (chord_scale) | `g_chord_cfg_obj_ptr`@`0x08016D58` | `chord_name_set`@6C7A, `chord_degree_set`@6CB4, **`chord_degree_lookup`@6CC8**, `scale_note_set`@6D10, `scale_contains_note`@6D3E | `g_chord_name_table_ptr`@6D5C (9×4-char), `g_chord_degree_table_ptr`@6D60 (13 bytes, per-degree chord), `g_scale_noteset_ptr`@6D64 (128-bit scale membership) |

**`scale_quantize_note`@0x080169B6 ★** = the quantizer: `if note<0x80 && (force||enabled){ pc=note%12; note += interval_map[pc]; }`. Called by **`arp_step_emit`** and the note-out builders → scale snaps both arp and live notes.
**`chord_degree_lookup`@0x08016CC8** decodes a `g_chord_degree_table_ptr[degree]` byte: `(b>>4)&3`=type {0=interval via `DAT_08016d68`, 2=interval via `DAT_08016d6c`, else 0x8000=none}, `b&0xf`=value → returns chord interval (16.16 hi).
**`chord_edit_handler`@0x0801ACF0 ☆** = the Scale-Chord/User-Chord **editor**: parses note(0x90/0x80) + CC(0xb0) into the chord/scale config (`g_chord_edit_cfg_ptr`@`0x0801AE24`); CC sub-nibble routes to `chord_degree_set`/`scale_note_set`/degree slots; `chord_slot_release`@0x0801ACB0 issues queued note-offs (state class 0xf7). Gated off when `arp_get_state()==1`.
**`held_note_apply_scale`@0x08016E4A** = arp-input seam: re-quantizes held notes via `scale_quantize_note` (caller `arp_held_note_add`).

## MIDI output / TX stack (2026-06-28, coverage) — mirror of the RX/ctrl-in path
| symbol | addr | role | conf |
|---|---|---|---|
| `midi_send` | `0x0800B3D0` | high-level note/CC/etc send → `midi_tx` | ★ |
| `midi_tx` | `0x0800B35C` | serializer: per-port obj (`p[0]`=ringbuf,`p[3]`=filter,`p[4]`=mode,`p[5]`=cable); mode0→USB-MIDI packet, else byte-stream (len 1/2/3 from status) | ★ |
| `midi_tx_sysex` | `0x0800B3F0` | **SysEx TX** (18 callers): frames `0xf0..0xf7`, emits USB-MIDI SysEx packet codes 4-7; used by all the extdata/config SysEx response builders | ★ |
| `usb_midi_packet_put` | `0x0800912A` | push a 4-byte USB-MIDI event packet into the TX ringbuf (checks ≥4 free) | ★ |
| `midi_byte_enqueue` | `0x080090F6` | push 1 byte into a TX ringbuf (head `p[2]`, tail `p[1]`, mask `p[3]`) | ★ |
| `ctrl_out_encode` | `0x08017940` | **output mirror of `ctrl_in_*`**: virtual class byte → MIDI status. High-nibble: 1=CC, 2=NRPN (0x65/100), 3=RPN (99/0x62), 4=PC(0xc0), 5=pitchbend(0xe0), 6=chan-pressure(0xd0), 0/0xe/0xf=note/poly-AT; specials 0xe0-0xe5/0xf6-0xf8 | ★ |
| `midi_out_forward` | `0x0801BBEC` | forward note/CC/PC out + update note-state store | ☆ |
This **answers note 26's open question** — the class byte that namespaces the `(class,index)`
value store maps directly to a MIDI message type on output (`ctrl_out_encode`'s switch). So the
control abstraction is symmetric: `ctrl_in_*` decode wire-MIDI→(class,index,value),
`ctrl_out_encode` encodes (class,...)→wire-MIDI.

## Control-smoothing / thinning engine (2026-06-28, coverage) — `ctrl_smooth_emit`
Continuous 14-bit controls (pitchbend/CC, virtual classes 0xe1/0xe3-0xe5/0xf7) don't emit
raw — they go through a **send-on-change + TX-throttle** engine so a fast knob sweep can't
flood the MIDI queue. State = a per-group **active-control tracking list** (3 groups × 32 slots):
| symbol | addr | role |
|---|---|---|
| `g_ctrl_track_count` | `0x08017874` | per-group active count (3 bytes) |
| `g_ctrl_track_keys` | `0x08017878` | 3×32×u32, key = `class<<16 \| index` |
| `g_ctrl_track_values` | `0x0801787C` | 3×32×u16, last-sent value per active control |
| `ctrl_track_find/add/remove` | `0x08017734`/`775A`/`77F4` | slot mgmt (find by key; add w/ cap 32; swap-remove) |
| `ctrl_track_value_set/get` | `0x0801782C`/`784E` | read/write the tracked last value |
| `ctrl_emit_gated` | `0x08017880` | emit a step via `ctrl_out_encode` only if TX load + an LFSR gate (`DAT_080178d8`) + change threshold allow |
| `ctrl_smooth_emit` | `0x08014CD6` | the engine: `delta=|new-old|`; branches on `tx_queue_load` — high load → throttle/drop, low → track+emit; (`DAT_08014f64`=per-control port-obj table ×8) |
| `ctrl_out_dispatch` | `0x08014DF8` | publish-subscriber: per destination, route by class → smooth path (`ctrl_smooth_emit`) for continuous, direct `ctrl_out_encode` for discrete; (callers incl. `midi_note_state_set`) |
| `ctrl_out_flush` | `0x08014E90` | sibling that `ctrl_track_remove`s each destination (teardown / value reset) |
| `tx_queue_load` | `0x0800B502` | TX ring occupancy (`ringbuf_used`) scaled → throttle level |
| `tx_free_headroom` | `0x0800B4E2` | TX ring free (`ringbuf_free`) scaled minus safety floor |
| `ringbuf_used`/`ringbuf_free` | `0x080091C2`/`91D0` | generic SPSC ring fill/free (`(head-tail)&mask` / `(tail-head-1)&mask`) |
**Next lead:** the `0x0801775a` register-arg loss means group-id/count fields are inferred;
the per-control port-obj table `DAT_08014f64` and the `0x08014ef4/f02/f10` iterator helpers are
still `FUN_`. Best confirmed live with `midi_capture.py` (sweep a 14-bit CC fast, watch
thinning).
**Observer idiom (recurring):** config objects expose `*_observer_add(cb)` storing a fn-ptr in an array; mutators loop `for i<count: cb[i]()`. The page-UI modules in **`0x08010xxx`** are the subscribers (next coverage lead — but it's mostly tiny vtable/stub thunks + a few large page handlers like `FUN_0801024e` 490B).

## Config / storage stack (Tier-1 deep-dive)
External **SPI NOR flash** (opcodes confirm it) holds config/custom-modes. Layered:
| layer | symbol | role |
|---|---|---|
| SPI xfer | `spi1_xfer`@09502, `spi1_dma_driver`@0953E | SPI1 (+DMA) primitive |
| flash HW (`serstor_hw.c`) | `serstor_flash_write_enable`@09E2C (WREN 0x06), `_erase`@09E98 (0xD8/0x20), `_write`@09F0C (0x02 page-prog), `_read`@09F60 (0x03), `_run`@09FBA (status-poll 0x05 + multi-page), `serstor_get_handle`@0A156 | SPI NOR driver |
| region pumps | `confstore_flash_pump`@0D76A (erase 0x21000), `confsys_flash_pump`@15DAC, `extdata_flash_pump`@17F14 | per-region async op state machines (ctx[3]=cmd 2=erase/3=write/5=read) |
| config sys (`confsys*.c`) | `config_init`@0DCC0, `confsys_init`@15B94 (boot load+validate, dual-bank CRC), `confsys_load_validate`@0A5B0, `confsys_obj_xfer`@15FF4 (vtable obj read/write) | config system |
| external (`extdata_*.c`) | (mostly unnamed) | read/write config over SysEx/USB |
Note: `extdata_msd`=USB mass-storage (fw-update drive), `extdata_upn`=user-product-number
(focusrite register URL), `extdata_upgrade`=firmware upgrade. Big unnamed config funcs
left: 0x080170F8 (1032B), 0x0801989A, 0x0800EC54 (MSD parser).

## Musical engine — arp / scale / chord (notes 19-20)
Arp engine @ `0x08013xxx`, **pad-configured** (no screen). Clocked by MIDI `0xF8`.
| symbol | addr | role |
|---|---|---|
| `g_arp_rate_divisors` | `0x08013B10` | `[3,2,6,4,12,8,24,16]` = 1/32..1/4 straight/triplet tick divisors (24 PPQN). ★★ **HW-VERIFIED 2026-06-27**: 1/16-straight measured = 6 clocks/step (210/211 gaps) via `scripts/midi_capture.py arp` |
| `arp_apply_rate` | `0x080137FE` | `rate*2+(straight?0:1)` → divisor → program clock → refresh LEDs |
| `arp_rate_get`/`arp_triplet_get` | `0x080134C0`/`0x080134DE` | read rate index / triplet flag |
| `arp_page_render` | `0x08013508` | light 16 pads for the arp page (`DAT_08013b00`=4 group colours) |
| `arp_control_handler` | `0x0801391C` | arp page input router (note 23). top row 0-3=group select→state+0xc; bottom 8-0xf=value→per-group handler |
| `arp_mode_select` | `0x08013B34` | **NOT the arp page** — drives a sibling struct (`DAT_08013e00`=`0x2000e648`), likely scale/fixed-chord page (note 23, unconfirmed) |
| `transport_button_handler` | `0x080133D4` | Play → MIDI start/stop |
| `held_note_update` | `0x08016A44` | maintain held-note linked list (`DAT_08016bf0`), arp input |
| `chord_degree_lookup` | `0x08016CC8` | 13-entry per-degree chord table → interval (see Scale/Chord engine section) |
| `scale_quantize_note` | `0x080169B6` | snap note to active scale (mod-12 + interval map); used by `arp_step_emit` + note-out |
| `control_dispatch` | `0x0800C72C` | hub: routes control/button events to all feature handlers (22 callees) |
| `midi_send`/`midi_out_forward` | `0x0800B3D0`/`0x0801BBEC` | raw MIDI out / forward+state |
Sibling table `[2,4,6,8,8,32,6]`@`0x0801367E` = gate/swing?

**Arp Controls PAGE UI (note 23, 2026-06-28) — fully traced press→config.** Two structs:
UI state `g_arp_state_ptr`@`0x2000e628` (+0 on, +2 held, **+0xc active group 0-3**) vs arp
config@`0x20001fac` (engine reads it). The `0x08013xxx` cluster never writes config — it
calls a bridge in the engine cluster. **4 groups** (proven: `DAT_08013b00` is a 4-entry
colour table, code after idx3): 0=Mode(purple,7cells `arp_type_select`), 1=Rate(orange `arp_rate_select`),
2=Octave(blue,5 `arp_octave_select`), **3=Rhythm(yellow,5cells pads8-0xc `arp_rhythm_select`)**. Each value
handler = fetch pressed value (`arp_value_fetch`→`arp_cfg_snapshot`) → **`switch` range-guard** → apply
(`arp_value_apply`→**`arp_cfg_apply`**). `arp_cfg_apply` writes config (`arp_cfg_copy`) then **calls
`rhythm_decode`(`0x080175B0`)** — i.e. the apply terminates in our Euclidean detour. CC 0x5b
path (`arp_cc_in_handler`) shares the same `arp_cfg_apply`. Render: `arp_page_render` Rhythm branch
paints only pads 8-0xc (`DAT_08013aec` dim / `DAT_08013af0` `ffff00` active); **pads 0xd,0xe,
0xf are FREE**. → Euclidean UI = widen the `arp_rhythm_select` guard (0..4 → more) + paint pads 0xd-0xf
in the render Rhythm branch. No new group/render branch needed.

**Arp RHYTHM engine (FOUND 2026-06-27, the rest/step machinery):** the `0x08013xxx`
cluster (arp_step, arp_mode_select, g_arp_state_ptr@`0x2000e628`) is UI/LED/flush ONLY.
The real step+rhythm engine is `0x08014xxx`/`0x08017xxx`:
| symbol | addr | role |
|---|---|---|
| `arp_step_emit` | `0x08014648` | per-step: consult rhythm; on HIT advance note ptr + emit. Driven by `main_task_tick` step-timer (`g_arp_state_ptr+4` countdown) |
| `arp_held_note_add` | `0x08014448` | note-on → held-note list + re-`rhythm_decode` |
| `rhythm_rest_decide` | `0x0801760A` | **returns 1=hit/0=rest**: `return mask >> (step & 0xff) & 1;` step ctr at state+0x10 wraps at period (state+8). Random uses LFSR (state+0). ★ |
| `rhythm_decode` | `0x080175B0` | `switch(config[+3])` → writes mask(state+4)/period(state+8). O=1/p1, OXO=5/p3, OXXO=9/p4, Random=flag, Deviate=`0x80-cfg[+9]`/p8. **movs immediates** (case2 body @`0x080175E2`). ★ |
| rhythm pattern state | `0x20001fe8` | +0 random-flag, **+4 mask (u32)**, **+8 period**, +0xc LFSR, **+0x10 step ctr**, +0x14 last-cfg+3 |
| arp config struct | `0x20001fac` | +0 rate-div, +1 mode, +2 octave, **+3 Rhythm sel** (CC0x5b), +4 latch, +7 gate%, +9 deviate, +0xa.. held-notes |
| CC arp-settings writer | `0x0801AAF0` | incoming CC ch0 0xB0 → arp config via `arp_cfg_apply`. **Full map (note 23):** 0x55 Mode(sw 0-6→+1), 0x56 Rate(1-7→divisor,+0), 0x57 Octave(≤3,+1→+2), 0x58 Latch(+4), 0x59 Gate(0-99→`(v<<7)/99`,+7), **0x5a Mutate**(clamp 0x22-0x5e,<<1,+6), **0x5b Rhythm**(sw 0-4 else 0,+3), 0x5d **Deviate**(+9). Device arp KNOBS send 0x5a/0x5d (Mutate/Deviate); **no knob is bound to Rhythm** (rhythm = pad row only on-device). |
**Euclidean = new mask values.** Inline only fits 8-bit masks (movs, period≤8). n=16 masks
(>0xFF) need movw → trampoline `rhythm_decode` to appended code + extend CC0x5b/UI clamps.
Note-advance-on-hit is native (matches "Euclidean skip-step" semantics). HW-verified.

## Pointers / leads to chase (still `FUN_`/`DAT_`)
| addr | role | conf |
|---|---|---|
| `0x0801B5B0` | caller of `velocity_curve_set` — likely SysEx/settings dispatcher | ☆ |
| `0x080126D0`,`0x080126EE`,`0x08012724`,`0x08012770`,`0x080127BC` | sibling `g_settings` handlers (found via `q.py xref 0x20002128`) | ☆ |
| `0x0800CEBC` | `led_desc_get_or_create` (used by velocity_curve_set) | ☆ |
| `0x0800F8E0` | installs a transform LUT (called by velocity_curve_apply) | ☆ |
| `DAT_0800CF98` | LED-descriptor manager: count `+0xc`, array ptr `_DAT_0800CF9C` | ☆ |

## Device-in-the-loop (hardware validation) — `scripts/midi_capture.py`
Black-box MIDI harness: drive + observe the live device at ms speed, NO flashing,
fully reversible. Turns static hypotheses into measured facts (note 21).
- **Routing:** standalone mode → keys/arp emit on **`MIDI Port` ch0**; DAW Port silent
  unless InControl is enabled. Note-offs arrive as `note_on velocity=0`.
- **Device free-runs MIDI clock (`0xF8`) on the MIDI Port even at idle** (120 BPM = 48
  ticks/s, 24 PPQN) → arp step rate is directly countable in clocks, no host clock needed.
- `midi_capture.py arp` counts `0xF8` between note-ons → reconstructs a divisor empirically.
- Subcommands: `ports`, `monitor`, `send` (raw/`--sysex` auto-wraps `F0 00 20 29 … F7`),
  `arp`, `sysexscan` (sweep SysEx cmd bytes, log responses → map the dispatcher).
- Validation backlog: full arp table (other 7 rates), scale/chord interval table (enable
  scale, play chromatic, capture quantized out), velocity curves (A/B the curve-select).
- Seen but unmapped: `control_change ch16 cc103` from a transport/round button.

## Open TODO (offline)
- [ ] SVD-Loader pass (`tools/svd/STM32F401.svd`) → register names in decompile.
- [ ] HAL BinDiff vs compiled CMSIS/HAL → auto-name library leaves.
- [ ] Decode remaining `g_settings` fields → find arp/chord/scale config.
- [ ] Find USB-MIDI RX → note-dispatch (the musical-engine gateway).
- [ ] Locate scale/chord/arp interval tables (scan_tables.py had candidates near
      `0x0800DE..`, `0x08010700`).
