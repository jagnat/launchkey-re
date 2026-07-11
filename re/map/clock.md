# Clock / tempo engine — the single 24 PPQN tick source

Mapped 2026-07-10 (static; ★ = code-verified, ☆ = strong inference). This is the timing
foundation for M4 (looper/generative): one tick counter drives MIDI-clock-out, arp steps,
and LED blink/pulse phase.

## Architecture (all ★ unless marked)

```
TIM2 ISR (1 kHz)          clock_engine_pump @0800B0BA          consumers (poll via
  g_ms_counter++   ─────▶  every ms: phase += 1000 µs;   ────▶  timer_elapsed diffs)
  @20002400                 phase ≥ period → TICK                • midi_clock_out_pump
                            (or drain ext ticks queued           • arp_step_emit
                             at +8 — statically dead)            • led_blink_phase_pump
```

- **`g_ms_counter` @`0x20002400`** — incremented by `TIM2_IRQHandler`@`0x08008378` at 1 kHz
  (a 2nd word @`0x20002404` is bumped alongside; no reader found). `delay_ticks_busy`
  @`0x08008360` busy-waits on it.
- **`clock_engine_pump`@`0x0800B0BA`** (main polled loop) converts elapsed ms → 24 PPQN
  ticks: phase accumulator (`+0xc`) += 1000 µs per ms; on `phase ≥ period(+0x10)` fire a
  tick → `g_clock_ticks`@`0x200014B8` (+0x20)++, and if transport running (`+0` byte),
  `g_clock_transport_ticks`@`0x200014B0` (+0x18)++ too.
- **Consumers never get callbacks** — each keeps a latch and diffs the shared counter with
  `timer_elapsed(latch, counter_ptr)` (`counter_latch_init` seeds the latch).
  `clock_get_tick_counter_ptr`@`0x0800B026` returns `&g_clock_ticks`.

## `g_clock_state` @ `0x20001498` (base ptr `DAT_0800b27c`)
| off | what | conf |
|---|---|---|
| +0 | transport running flag | ★ |
| +1 | resync flag (skip next tick emit, clear phase) | ☆ |
| +2 | external-clock-active | ★ |
| +3 | estimator sub-state | ☆ |
| +4 | ptr to ms source (= `g_ms_counter`, set by `clock_engine_init`@`0x0800AFD0`) | ★ |
| +8 | pending external-tick queue (count) | ★ |
| +0xc | phase accumulator, µs | ★ |
| +0x10 | **tick period, µs/tick** — clamp [1000, 1000000]; 120 BPM = 20833 | ★ |
| +0x14 | µs since last external tick (timeout ⇒ fall back to internal) | ★ |
| +0x18 | transport tick counter (`g_clock_transport_ticks`) | ★ |
| +0x1c | ms latch for the pump | ★ |
| +0x20 | raw tick counter (`g_clock_ticks`) — THE 24 PPQN clock | ★ |
| +0x24/+0x98/+0xbc/+0x190 | 4 external-tempo estimator windows (len 0x18/4/0x30/8) | ☆ |

## Tempo
- **period_us = 2,500,000 / BPM** (`= 60e6 / 24`; constant @`0x0801B7C4`).
- **`sysex_tempo_set`@`0x0801B770`**: SysEx cmd byte `0x0A`, 14-bit value (`msb*128+lsb`)
  = BPM, clamped **[20, 600]**, rounded division → `clock_set_tick_period_us`@`0x0800B08C`
  (which no-ops while external clock active). ☆ untested on HW — validation backlog.
- Second tempo-set caller `FUN_0801a4a4` (unread; likely another SysEx/extdata path).
- `clock_get_tick_period_us`@`0x0800B086` reads it back (arp_step_emit uses it for gate time).

## Transport (start/stop) — statically DEAD on the Mini
- `clock_transport_start`@`0x0800B072` (zero position + run), `_continue`@`0x0800B068`,
  `_stop`@`0x0800B07A`, `clock_ext_tick_rx`@`0x0800B0AA` (queues external 0xF8):
  **zero static callers**, and their Thumb addresses appear nowhere in flash as pointers —
  inherited shared-codebase code, unwired on this product. ⇒ transport never "runs";
  `g_clock_transport_ticks` stays 0; the arp times itself off raw `g_clock_ticks` only.
- Consequence for mods: **the transport machinery is free real estate** — a looper could
  call `clock_transport_start/stop` itself and use `g_clock_transport_ticks` as its song
  position, at zero stock-behaviour risk (verify on HW first — backlog).
- The Play button (ids 0x17/0x62, `transport_button_handler`@`0x080133D4`) only **sends**
  0xFA/0xFC to the host via a local toggle byte (struct @`DAT_080134b8`); it never touches
  the engine.

## MIDI clock out — `g_midi_clock_out_state` @ `0x2000E618`
`midi_clock_out_pump`@`0x0800B84E` (main loop): diff `g_clock_ticks`, send one `0xF8` per
tick via `midi_send(port, 0xf8, 0, 0)`. Struct: +0 enable (`midi_clock_out_enable`
@`0x0800B842`, driven by `settings_apply_all` — the "MIDI Clock" device setting),
+1 suppress (`midi_clock_out_suppress`@`0x0800B848`), +4 tick-counter ptr, +8 midi port,
+0xc latch. Matches the measured free-running 0xF8 @120 BPM (validation.md).

## LED blink/pulse sync
`led_blink_phase_pump`@`0x0800BA74` (main loop): beat phase = ticks mod **0x30** (48 ticks
= 2 beats); while "transport running" it re-derives phase from transport ticks, else
free-runs on wall ms (approx). Per LED it reads the attr byte (mode bits: 1=blink
half-cycle, 2+=pulse via fade tables `DAT_0800bba0/a4/a8`) and composites the frame —
this is why pulsing pads breathe in tempo. `led_blink_phase_init`@`0x0800BA5C`.

## Looper-relevant summary (M4)
- Tick source to poll from our hook: `g_clock_ticks`@`0x200014B8` (u32, 24 PPQN), via own
  latch + `timer_elapsed` — exactly how stock consumers do it.
- Tempo: read `clock_get_tick_period_us()`; set via `clock_set_tick_period_us(2500000/bpm)`.
- Song position: `g_clock_transport_ticks` + `clock_transport_start/stop` — unused by stock,
  ours to drive (HW-verify first).
- ms clock for non-musical timing: `g_ms_counter`@`0x20002400` (1 kHz).
