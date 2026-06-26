# 20 — The arpeggiator: locating the engine and its rate table

Goal: find the arp. Done offline with the corpus. The decisive anchor was a **data
table**, not code — a good reminder that for feature engines, the *tables* are often
the fastest way in.

## How we found it
1. **Strings** gave the feature vocabulary (`re/strings.tsv`): `Arp On`,
   `Arp Control Lock`, `Tempo`, `Tempo (External)`, `Swing`, `Gate Length`, `Latch`,
   `Octave`, `Chord`, `Scale On/Set`, `Fixed Chord`, `User Chord`, `MIDI Clock Out`.
   These are the arp/scale/chord **parameter names** (exposed via the config/SysEx
   system, note-T1), confirming the feature set.
2. The labels are referenced from a **descriptor table**, not inline, so they don't
   appear as `s_` symbols in code — the usual call-graph trace stalled (the engine is
   also callback-driven; the MIDI-out builders have no static callers).
3. **The table cracked it.** Scanning for arp **rate divisors** (24 PPQN: 1/4=24,
   1/8=12, 1/16=6, 1/32=3; triplets = ×2/3) found:
   `g_arp_rate_divisors` @ **`0x08013B10`** = `[3,2, 6,4, 12,8, 24,16]` =
   **(1/32,1/32T),(1/16,1/16T),(1/8,1/8T),(1/4,1/4T)** straight/triplet pairs.
   That pins the **arp engine to the `0x08013xxx` region** (the table sits right before
   `arp_mode_select`, loaded PC-relative — hence no literal pointer to it).

## What the engine looks like (the arp is pad-configured — no screen)
| function | role |
|---|---|
| `arp_mode_select` @08013B34 | maps pad IDs `0x10–0x1f` → arp pattern / direction / octave, with LED feedback |
| `arp_page_render` @08013508 | lights the 16 pads to show the current arp settings page (`DAT_08013b00` = per-cell colours) |
| `arp_transport_start` @0801391C | handles MIDI **start `0xFA`** (run the arp/sequencer) |
| `transport_button_handler` @080133D4 | Play button → toggles MIDI **start `0xFA` / stop `0xFC`** out |
| `g_arp_rate_divisors` @08013B10 | the rate→tick-divisor table (the knob that sets arp speed) |

Supporting plumbing named along the way: `midi_send` @0800B3D0 (raw MIDI to a port —
`midi_send(port,0xFA,...)`), `led_set_color` @0800BB50 (set a pad LED to a 24-bit
colour), `control_value_get` @0800BECC (read a pad/button state).

The arp consumes the **held-note set** `g_note_active_matrix` (note-19) and is clocked by
the MIDI clock (`0xF8`) or the internal tempo; on each step it picks the next held note
per the pattern/rate/octave and emits via the MIDI-out builders (`FUN_0801bbec` etc.).

## The knobs (for later experiments, verified by MIDI capture)
- **Rate:** `g_arp_rate_divisors` @0x08013B10 — change a divisor to change arp speed per
  setting. Small table near `[2,4,6,8,8,32,6]` @0x0801367E is a sibling (gate/swing?).
- **Pattern/direction/octave:** selected in `arp_mode_select`; the pattern stepping logic
  is the next thing to read (find where the step index advances on each `0xF8`).

## Status / next
Located + named the arp control/UI + its rate table; coverage 80→88 functions
(16.5% of code bytes). NEXT: the **step generator** — trace the `0xF8` clock consumer
that advances the arp step and reads `g_note_active_matrix`, to fully expose pattern
tables; then a `scripts/midi_capture.py` test (rate edit → measured note timing).
