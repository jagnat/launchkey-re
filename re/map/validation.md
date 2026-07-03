# Device-in-the-loop validation — `scripts/midi_capture.py`

Black-box MIDI harness: drive + observe the live device at ms speed, NO flashing, fully
reversible. Turns static hypotheses into measured facts (note 21). Prefer this over the slow
flash→eyeball loop. Run with `.venv/bin/python` (has mido).

- Subcommands: `ports`, `monitor`, `send` (raw/`--sysex` auto-wraps `F0 00 20 29 … F7`),
  `arp` (counts `0xF8` between note-ons → reconstructs a divisor empirically),
  `sysexscan` (sweep SysEx cmd bytes, log responses → map the dispatcher).

## Measured routing facts
- Standalone mode → keys/arp emit on **`MIDI Port` ch0**; DAW Port silent unless InControl is
  enabled. Note-offs arrive as `note_on velocity=0`.
- **Device free-runs MIDI clock (`0xF8`) on the MIDI Port even at idle** (120 BPM = 48 ticks/s,
  24 PPQN) → arp step rate is directly countable in clocks, no host clock needed.
- **The arp CC handler (0x55-0x5d, ch0) listens on the DAW PORT, not the MIDI Port** — an
  earlier "inconclusive" verdict was just the wrong port.
- Arp note-ons appear only when actually streaming; use **Latch + a held chord** so the arp
  free-runs for capture.
- Physical knobs (not held-Arp) emit pot CCs `0x15..0x1c` on **ch16 (0xBF), DAW port**.
- Seen but unmapped: `control_change ch16 cc103` from a transport/round button.

## Validation backlog
- Full arp rate table (other 7 rates; 1/16-straight = 6 clocks/step already ★★).
- Scale/chord interval table (enable scale, play chromatic, capture quantized out).
- Velocity curves (A/B the curve-select).
