# Firmware map — session init + index

Read THIS file at session start. It is the distilled current state + an index.
Deep reference lives in `re/map/*.md` topic sheets — open only the sheet(s) the task needs;
query code via `scripts/q.py`. Do not bulk-load `re/firmware.c`.

## Current status (rewrite in place each milestone — keep ≤40 lines, no history)
**Coverage:** see `re/coverage.txt` (updated at each corpus regen).

**Shipped + HW-validated (2026-07-01): Euclidean arp, standalone.** k via the Arp Rhythm pad
row (free pads 0xd/0xe/0xf → E(4/5/6,n)), n via the Deviate knob while Arp is HELD, DAW-port
CC 0x5b selects presets 5-10. Details + formulas: `re/map/arp.md`. Keeper mods (in
`mods/build.py` MODS): `led-palette-42-red`, `cc5b-rhythm-clamp-0to10`, `euclid-rhythm-engine`,
`arp-rhythm-guard-widen`.

**Active task: custom pad page (own the grid with our own UI).**
- RENDER SEAM PROVEN on HW (2026-07-02): hook `main_task_tick`'s empty slot @`0x0800C95A`,
  per pad `led_attr_set_direct` + `led_set_color`, preserve r4/r5/r6. Recipe: `re/map/leds.md`.
- INPUT SEAM ★★ HW-PROVEN (2026-07-03, ctlscope v3): `control_value_emit(id,value)`
  @`0x0800F840` publishes the WHOLE surface with discrete ids — pads 0x00-0x0F, buttons
  0x10-0x19, strips 0x36/37, knobs 0x38-0x3F, keys 0x80-0x98 (+pad pressure as values).
  Full map + hook recipe: `re/map/input.md`. Serves page toggle, in-page input, knob→arp.
- Mod scratch RAM = `0x2000F000`+ (statics end ~`0x2000E771`; `0x2000DD37` is poisoned — see
  dead ends). Page flag can live there.
- M1+M2 HW-VALIDATED (2026-07-03): first **C payload** (`mods/c/ui.c` + `mods/asm/ui_glue.s`;
  build.py compiles/links multi-src append blocks, multi-detour via symbols, rejects
  .data/.bss). **Shift+pad8 toggle** → mode 1 home page; dispatch gate blocks stock UI
  (recipe: `re/map/input.md`). State struct @`0x2000F000`.
- M2.1 HW-VALIDATED (2026-07-03): emit tap SWALLOWS ids <0x80 while the layer is active
  (skip the fan-out; keys ≥0x80 pass; releases always pass) — full surface capture, no
  MIDI/LED leaks, no ghost Shift latch.
- M3 HW-FLASHED (2026-07-12): **Euclid app** (mode 2, via home pad0). 16-pad live pattern
  view (playing step highlighted from `RHY->step`), Fixed Chord = back home. Engine PORTED
  TO C (`mods/c/rhythm.c`, replaces rhythm_decode.s → attic): UI override > pad-row presets
  5-10 > stock 0-4; stock/DAW selector change cancels the override.
- M3.1 HW-VALIDATED (2026-07-12): euclid-knob fix. Root cause: standalone knob continuous
  values ride the 4th fan-out `control_value_emit_4@0x0800F8A2` (subscriber
  `surface_value_handler@0x0800C1B6` → ctrl_in pot stages = the pot-CC source); F840 carries
  only discrete presses, so the M2.1 swallow never saw them. Fix: 2nd prologue detour
  `ui_tap_emit4` (same recipe, resume `0xF8A6|1`) → `ui_on_value(id,value)` — swallows ids
  <0x80 while the layer is active + drives k/n/rot (a knob edit also reclaims the euclid
  override). MEASURED on DAW port: knob sweeps on the euclid page = zero `bf 1x`; after layer
  exit = clean stock `bf 15` runs. User-validated audible (2026-07-12): pattern sweeps + step
  marker moves with arp on. Seam truth + subscriber map: input.md.
- M3.2 HW-VALIDATED (flashed 2026-07-25, user-confirmed incl. M3.2a) — closes M3.1's arp UX gap, both ways at
  once. (a) Arp passthrough: while Arp (id `0x15`) is held or the stock arp panel is latched
  (`0x2000E628`+0), stock owns the whole surface — both emit taps stop swallowing, the dispatch
  gate lets the layer-0 chain run, `ui_frame` cedes the pads (clears direct bits) so
  `arp_page_render` paints; held-Arp knob→cfg routing returns free (same emit_4 chain).
  M3.2a (HW-found, fix flashed 2026-07-25): input and pads need SEPARATE predicates —
  `arp_stock_input()` = held-or-latched (taps/gate, hands over on the press), but
  `arp_stock_pads()` = the LATCHED panel byte only. Ceding pads at press time clears our
  direct bits while the palette layer still holds idle content → red fill (`led-palette-42-red`)
  for the whole stock hold-timer window, until `arp_page_render` fills that layer.
  (b) Auto-enable: Euclid app entry calls `arp_set_enabled(1)` if off (idempotent, its tail
  re-runs our `rhythm_decode` detour; override survives — selector unchanged) and remembers via
  `arp_auto`; exit undoes only that, a manual Arp press in-app clears the flag. Gate verdict
  moved asm→C (`ui_dispatch_block`), so `ui_glue.s` is now pure register marshalling.
  NEXT: M4 looper/bounce/generative.
- M4 PREP (2026-07-10): **clock/tempo engine fully mapped statically** (`re/map/clock.md`):
  one 24 PPQN tick counter `g_clock_ticks`@`0x200014B8` drives clock-out + arp + LED pulse;
  tempo = `clock_set_tick_period_us(2500000/BPM)`; transport start/stop machinery exists but
  is UNWIRED on the Mini → free for a looper song-position. HW checks queued in validation.md.

**Device currently runs (flashed 2026-07-25):** M3.2a = current `mods/build.py` MODS (3 inline
keepers + `ui-layer` C block M1+M2.1+M3+M3.1+M3.2a), image 89,328 B ending `0x0801DCF0`.
Shift+pad8 → home; home pad0 → Euclid app (auto-enables arp); knobs 1/2/3 = k/n/rot; hold Arp
→ stock arp menu. Full surface capture incl. knobs, minus the M3.2 arp passthrough.

**Direction (2026-07-03, user-ratified):** page/menu foundation FIRST — looper, note-bounce,
and generative modes all need latch-in/out pages + owned input, so they queue behind it.
Euclid finishes as the first app on the new page (live pattern view, knobs=k/n/rot per
`re/map/arp.md` "Design direction"). Full-custom C firmware rejected (USB/scan/no-SWD risk);
middle path instead = C-authored mod payloads on the stock "OS". Looper last (timing + RAM).

**Constraints:** SWD ruled out (no test points; user won't open unit). Never flash without an
explicit user go-ahead.

## Verified dead ends — do NOT re-attempt (details in the topic sheets)
- `pad_page_render_dispatch`'s empty slots = DAW/host page path; never runs at standalone idle.
- `arp_get_state()` is a tri-state VIEW state, not arp-on; use `arp_is_enabled`@`0x080148B0`.
- `led_set_color` without `led_attr_set_direct` loses to the palette layer at idle.
- Knobs turned WITHOUT holding Arp never reach arp cfg (emit pot CCs 0x15-0x1c/ch16 only;
  InControl enable `9F 0C 7F` doesn't change that — Ableton bridges them in software).
- Arp-panel pads 6/7 as custom toggles: `arp_control_handler` ignores them.
- `0x2000DD37` as a scratch/debug byte: inside live statics, firmware overwrites it every scan
  (poisoned BOTH early pad-id scopes into the false "param_1 ≠ pad id" verdict). Mod scratch
  RAM = `0x2000F000`+ (see `re/map/leds.md`).
- cfg[9] (Deviate) as a home for n: double-duties as a timing/swing param.
- Capturing standalone knob VALUES at `control_value_emit`@F840: they ride `emit_4`@F8A2 only
  (F840 = discrete presses/touch edges) — hook both seams for full capture (input.md).

## Topic sheets (`re/map/`)
| sheet | contents |
|---|---|
| `leds.md` | LED compositor (2 layers + direct bit), pad-page render architecture, custom-page recipe, post-mortems |
| `arp.md` | arp+rhythm engine, arp config struct, CC map, shipped Euclid mod, knob routing truth, arp page UI, design direction |
| `input.md` | control-surface scanner (pots/strips/pads ADC path), MIDI input router, control-mapping (`ctrl_in_*`) layer |
| `clock.md` | clock/tempo engine: 24 PPQN tick source, tempo set/get, (dead) transport, MIDI-clock-out pump, LED blink phase — the M4 timing foundation |
| `midi.md` | USB-MIDI RX path, TX stack, `ctrl_out_encode`, smoothing/thinning engine |
| `scale-chord.md` | scale/chord engine, quantizer, chord editor |
| `system.md` | boot, hardware drivers, ISRs/vectors, `g_settings`, velocity, config/SPI-NOR storage, open leads |
| `validation.md` | MIDI black-box harness facts (ports, free-running clock, measured routing), backlog |
Also: `re/hardware.md` (board/pin map), `re/README.md` (corpus format + regen workflow).

## Quick reference
| region | addr | notes |
|---|---|---|
| App load base | `0x08008000` | ★ stock image = 88,088 B, ends ~`0x0801D818`; appended mods go in the flash tail after it |
| Flash data/const | ~`0x0801A000`+ | ★ palette, velocity curves, tables |
| SRAM | `0x20000000`–`0x2000FFFF` | ★ 64 KB; init SP `0x2000FFF8` |

Most-used symbols (full tables in the sheets):
| addr | name | what |
|---|---|---|
| `0x0800C914` | `main_task_tick` | per-frame idle loop; empty hook slot call-site @`0x0800C95A` (a 2nd, `bl nullsub_080081f4`, is unlocated-but-present in the chain) |
| `0x0800BB50`/`0x0800BB6C` | `led_set_color` / `led_attr_set_direct` | paint a pad (direct bit first!) |
| `0x080175B0` | `rhythm_decode` | our Euclid detour site |
| `0x20001fac` | arp config struct | +3 rhythm sel, +6 mutate, +9 deviate |
| `0x2000e628` | `g_arp_state_ptr` | +0 arp-panel-active, +0xc active group |
| `0x0800C72C` | `control_dispatch` | input event hub (22 callees) |
| `0x0801391C` | `arp_control_handler` | arp page input router |
| `0x0800B3D0` | `midi_send` | high-level MIDI out |
| `0x20002128` | `g_settings` | device settings struct |

**Naming convention:** semantic names (e.g. `arp_step_emit`) = identified roles. `arp_3004` /
`scale_6c8` style = module-prefixed placeholders (module confirmed, role unread). `j_<fn>` =
forwarder thunk, `nullsub_<addr>` = provably-empty — both auto-classified by
`scripts/classify_stubs.py` (mechanical, accurate). Confidence marks: ★ verified,
☆ strong inference, ? guess.

## Maintenance rules (how this stays cheap)
- **Rewrite the status section in place** — current truth only, ≤40 lines. Never append
  checkpoints, corrections, or "the above is WRONG" — resolve to the new truth and delete the
  old. History = git log + `notes/NN-*.md`.
- A proven dead end gets ONE line in the dead-ends list (+ detail in its topic sheet if the
  mechanism matters).
- New durable facts go in the right `re/map/*.md` sheet; new names go in `re/symbols.tsv` +
  corpus regen (see `re/README.md`), then rerun `scripts/classify_stubs.py`.
- **The sheets follow the same rule:** when a fact is disproven, replace it with the new truth
  and delete the old — never leave "⚠ superseded/WRONG" annotations for a later reader to
  reconcile. Keep a failure only as a post-mortem/dead-end entry, clearly labeled as such.
- This file stays under ~120 lines; a new subsystem gets a new sheet + one index row here,
  never a new section in this file.
- Coverage numbers live in `re/coverage.txt` only — don't hand-copy them around.
- Commit `re/` + `mods/` at each milestone (ask the user first) — uncommitted state is how
  MAP, build.py, and the device drift apart.
