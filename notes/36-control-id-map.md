# 36 — The control-id map: the whole surface, measured

## The debug byte was the bug

Note 35 ended with ctlscope v2 flashed and high hopes. The readout came back
broken in a maddeningly familiar way: any bottom pad showed 8, any top pad
showed 0 — *the exact signature that killed the v1 scope at a completely
different hook layer*. Two different hooks, same wrong answer. That convergence
was the tell: the common factor wasn't the hook, it was the **debug byte**.

`0x2000DD37` had been picked as "LED attr array tail, safe while pad 0x7f is
unused". A corpus sweep of every `0x2000xxxx` reference showed firmware statics
extend to ~`0x2000E771` — the byte sits deep inside live data, and some
pad-row-related writer stores `id & 8`-shaped values into it on every scan.
Both scopes wrote their answer; the firmware overwrote it milliseconds later;
we read the firmware's value and blamed our hooks. The v1 conclusion
("param_1 is not the pad id, the id travels in r4") went into the map as a
dead end — and it was an *artifact*. Lesson one: **a diagnostic is only as
trustworthy as its scratch memory.** Lesson two: when two independent
instruments agree on a bizarre result, suspect what they share.

The fix: v3 moved the debug pair to `0x2000F000` — a region no code references,
2 KB above the last static, 4 KB below the initial stack pointer. That's now
the official mod-scratch region (MAP.md); the future page flag lives there too.

## Meanwhile, the corpus already knew the answer

While hunting, the control-type table surfaced: `g_control_type_tbl` @
`0x0801C7D0`, 256 bytes, `control_type_get(id)` = `tbl[id]`. It implied pads
were ids 0x00–0x0F all along. v3 on hardware confirmed it, and the user
measured the entire surface in one sitting:

| ids | control |
|---|---|
| 0x00–0x0F | 16 pads, reading order (top row 0–7, bottom 8–15) |
| 0x10–0x19 | Scene Launch, Stop/Solo/Mute, Transpose, Oct+, Oct−, Arp, Fixed Chord, Play, Record, Shift |
| 0x36, 0x37 | pitch / mod touch strips |
| 0x38–0x3F | the 8 knobs |
| 0x50–0x58 | 9 fader slots — nothing on the Mini; almost certainly the bigger Launchkeys' 9 faders (shared scan config) |
| 0x80–0x98 | the 25 keys, one id per semitone |

Two guesses died on contact with the data, both worth remembering:

- **"pot_scan" scans the keybed, not pots.** It emits `idx|0x80` — which the
  measurement shows is the *key* id space. Renamed `keybed_scan`. The knobs are
  ids 0x38–0x3F, scanned by `control_press_scan`'s analog path at standalone.
- **The type-1/2 pattern at 0x80+ is a piano keyboard.** The "unclear
  alternating 1/2" region decodes as white-key=1, black-key=2, repeating per
  octave. A keyboard layout was sitting in a type table looking like noise.
  (This also nails `control_velocity_scan`'s type-6/7 domain as knobs/faders in
  InControl mode — not pads.)

And a bonus with real design consequences: **pad pressure streams through the
seam** (the green value row tracked finger pressure), and so do key events.
Custom modes can be pressure-expressive and can see the keybed — without
touching the MIDI path.

## Where this leaves us

The custom-page platform is now fully de-risked at both ends:

- **Render**: `main_task_tick` empty slot → direct-layer paints (note 33/35).
- **Input**: one prologue detour on `control_value_emit` sees every control on
  the surface with a clean id. Measured, not inferred.

Next: pick the page toggle (a button in 0x10–0x19 or a Shift+pad chord — the
open question is co-existing with the stock handler for that control), put the
page flag in `0x2000F000`-land, and build the menu system as the first
C-authored payload (build.py grows a C `append` variant). Then ctlscope
retires and the attic gets its third diagnostic.
