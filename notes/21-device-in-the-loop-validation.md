# 21 — Device-in-the-loop: validating the firmware against the real hardware

Up to now every finding was either *static* (read out of the decompile / corpus) or
confirmed by the slow **flash → eyeball** loop (note 16). With the keyboard on the
desk, there is a third, much faster source of ground truth that needs **no flashing
and carries no risk**: the device is a MIDI black box we can both *drive* and
*observe* at millisecond resolution. This note builds that harness and uses it to
turn one static hypothesis — the arp rate-divisor table — into a **measured fact**.

## The reframe (why this is the accelerator)

A hardware controller's whole job is to emit MIDI in response to physical input. That
means its externally-visible behaviour is *fully observable* over USB-MIDI, live, with
exact timing. So instead of:

> change firmware → flash (~40 s) → watch the pads with your eyes → guess

we can do:

> poke an input (or just hold a key) → **capture the MIDI out** → *measure* it

No image is modified, so there is nothing to recover and no way to brick anything.
This replaces eyeballing with numbers and collapses the iteration time from ~40 s to
milliseconds. It is the single biggest lever for *validating* what we already believe
and for *growing coverage* with confidence.

## The harness — `scripts/midi_capture.py`

A thin wrapper over `mido` (rtmidi backend). Subcommands:

- `ports` — list visible in/out ports.
- `monitor [--raw]` — timestamped log of everything the device emits.
- `send --hex … | --sysex …` — send raw bytes; `--sysex` auto-wraps the body in the
  Novation envelope `F0 00 20 29 … F7`.
- `arp` — capture an arp run and measure **clocks-per-step**.
- `sysexscan` — sweep SysEx command bytes and log responses (maps the dispatcher).

It is deliberately also usable from `python -c` for one-off experiments.

## What the device tells you for free

A 4-second idle capture (touching nothing) already taught us three things:

1. **The device free-runs a MIDI clock (`0xF8`) on the MIDI Port even when idle** —
   ~48 ticks/s = **120 BPM at 24 PPQN**. This is the key enabler for the arp test: the
   step rate can be measured in *clock ticks*, an exact integer, with no host clock to
   set up.
2. A two-port capture (MIDI Port vs DAW Port) while pressing keys showed **notes come
   out the `MIDI Port` on channel 0; the DAW Port stays silent** in standalone mode
   (it only carries traffic when InControl/DAW mode is enabled). Knowing the routing
   up front avoids the "0 note-ons captured" dead end.
3. **Note-offs arrive as `note_on velocity=0`** (running status) — so the analyzer
   counts only `velocity > 0` as a step onset.

A freebie also fell out: a transport/round button emits `control_change ch16 cc103`
— logged for later control-map work.

## The experiment: confirm `g_arp_rate_divisors`

Static finding (note 20): `g_arp_rate_divisors` @ `0x08013B10` =
`[3,2, 6,4, 12,8, 24,16]` = straight/triplet tick-divisor pairs for 1/32,1/16,1/8,1/4
at 24 PPQN. The engine selects `g_arp_rate_divisors[rate*2 + (straight?0:1)]` as the
**number of clocks per arp step**.

Because the device emits *both* its clock and the arp note-ons on the same port, that
divisor is **directly observable**: count `0xF8` ticks between consecutive note-ons.

Procedure: Arp ON, rate **1/16 straight**, hold a chord, capture 40 s.

```
captured 2354 msgs, 1920 clocks, 212 note-ons
clocks-between-note-ons histogram:
    6 clocks: 210
  123 clocks:   1
=> modal clocks/step = 6   (24 PPQN: 6 = 1/16)
```

**210 of 211 step-gaps were exactly 6 clocks** — precisely the table's 1/16-straight
entry. The single 123-clock gap is the moment the chord was re-grabbed. The table is
now **★★ hardware-verified**, not merely inferred. (The remaining seven rate/triplet
cells are the same one-capture-each test — backlog, not done yet.)

## Lessons / method (reusable)

- **Observe before you drive.** A no-touch idle capture reveals the clock, the PPQN,
  and the message vocabulary for free. Always baseline first.
- **Find the routing before measuring.** A quick dual-port capture pinned notes to
  `MIDI Port` ch0; assuming the wrong port is how the first arp run got 0 note-ons.
- **Measure integers, not eyeballs.** Counting clock ticks gives an exact divisor with
  a clean histogram — far stronger evidence than "the timing looked about right."
- **This generalises.** Same pattern validates the rest of the musical engine without
  flashing:
  - *Scale/chord interval table* (`scale_chord_lookup`@`0x08016CC8`): enable scale,
    play chromatic, capture the quantized/expanded output.
  - *Velocity curves* (LUT @ `0x0801a158`): A/B the curve-select control, capture
    output velocities.
  - *SysEx command surface* (dispatcher candidate `0x0801B5B0`): `sysexscan` sweeps
    command bytes and logs responses → empirically maps the command table, then each
    command binds to its handler. (Read-back/query commands first; treat
    unknown bytes as potentially state-changing.)

## Status

- `scripts/midi_capture.py` added. `re/MAP.md` gains a "Device-in-the-loop" section and
  marks `g_arp_rate_divisors` HW-verified.
- NEXT (device present): finish the arp divisor table (7 more captures); scale/chord
  interval capture; then `sysexscan` to grow config/SysEx coverage.
