# 38 — The knob bug: one surface, four publish seams (M3.1)

## The symptom

M3 shipped the Euclid app: own the pad grid, knobs 1/2/3 = k/n/rot. On hardware,
the pads worked perfectly — but turning a knob on the honey-colored Euclid page
(a) still drove track volume in the DAW and (b) never moved the pattern. The
surface we thought we had fully captured… wasn't.

## Why this was surprising

M2.1's capture rested on what looked like a rock-solid measured fact: ctlscope
v3 had watched `control_value_emit@0x0800F840` and seen *every* control id go
by — pads, buttons, strips, keys, and yes, knobs 0x38–0x3F. So we hooked that
one function, swallowed everything below 0x80, and called the surface owned.

The trap: **seeing an id at a seam is not the same as seeing that control's
*data* at that seam.** A knob shows up at F840 exactly once per touch — the
discrete "this control became active" edge, with a velocity-flavored value.
Its actual *position stream* never goes there. We had proven coverage of ids
and silently inferred coverage of events.

## What the scanner actually does

`control_press_scan` conditions every control each tick and publishes through
**four sibling fan-outs** (same shape: count byte + up to 8 callback ptrs, each
called as `cb(r0=id, r1=value)`):

| seam | carries |
|---|---|
| `control_value_emit` @0x0800F840 | discrete presses (pads w/ velocity, buttons, key strikes) |
| `control_value_emit_2` @0x0800F85C | analog touch/activation edges |
| `control_value_release` @0x0800F884 | releases |
| `control_value_emit_4` @0x0800F8A2 | **continuous values** — knobs, strips, pressure (Δ>0x40 hysteresis, 0..0xFFFF) |

The design makes sense from the firmware's point of view: most consumers only
care about button-like events; the few that want streams subscribe to the
value seam separately. Our mistake was assuming one seam was "the" backbone.

## Walking the registration (the decisive move)

The static call graph was blind here — subscribers are registered through
pointer tables, so `q.py callers` showed nothing. The unlock was going the
other way: find the *registrar* stubs (`control_subscribe_*`, right next to
the fan-outs), then grep `xrefs.tsv` for calls into their forwarder thunks.
Two init functions fell out:

- `control_subscribers_init@0x0800C200` — the standalone set. The emit_4
  subscriber is `surface_value_handler@0x0800C1B6`, which runs the
  `ctrl_in_*` pot stages → `midi_note_state_set` → `ctrl_out_dispatch` —
  **this is the factory that makes the ch16 `BF 15..1C` pot CCs.**
- `incontrol_subscribers_init@0x0800C4B4` — an InControl-only mirror
  (`route_is_incontrol`-gated → dead in standalone).

That closed the case without a diagnostic flash: only ONE standalone consumer
of the value stream produces MIDI, so swallowing that one seam provably kills
the leak, and tapping it provably delivers the knob values we were missing.

## The fix (and why it was cheap)

Novation's compiler emitted `control_value_emit_4` with the *same prologue
bytes* as `control_value_emit` (`push {r3-r7,lr}; mov r4,r0`) and the same
quirky epilogue (`pop {r0,...,pc}` returns the caller's r3 in r0). So the
battle-tested F840 detour recipe transplanted byte-for-byte: `ui_tap_emit4`
is a 34-byte clone that calls `ui_on_value(id, value)` and either swallows
the fan-out or replays the two displaced instructions.

`ui_on_value` is where knob handling now lives — moved out of `ui_on_press`,
which could never have received it. One extra nicety: a knob edit re-asserts
the euclid override, so a DAW selector change can't leave the page deaf.

## Measured result

DAW-port capture, one 40s window: knob sweeps on the Euclid page = **zero
bytes**; exit the layer, sweep again = clean stock `bf 15 00→7f` runs. Leak
dead, stock behavior intact, pattern follows the knobs.

## Lessons

1. **"HW-proven" inherits the scope of the experiment.** ctlscope v3 proved
   *which ids exist*, not *which seam carries which event kind*. Write down
   what a measurement actually demonstrates, not the generalization.
2. **When the call graph goes dark, walk the registration.** Publisher/
   subscriber firmware hides its wiring in RAM tables; the registrars and
   their literal pools are the static ground truth.
3. **Symmetric firmware pays twice.** Because the four fan-outs are clones,
   one verified hook recipe covered the new seam with zero new risk.
