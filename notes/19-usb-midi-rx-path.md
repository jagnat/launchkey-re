# 19 — Finding the USB-MIDI RX → note-dispatch path (the musical-engine gateway)

Goal: locate where incoming MIDI enters the firmware and gets dispatched, because
every musical feature (arp, scale, chord, pads) hangs off that path. Done entirely
offline with the `re/` corpus + `q.py` — zero Ghidra launches for the investigation.

## The break: the firmware kept its `__FILE__` strings
`q.py str midi` (really a grep of `re/strings.tsv`) surfaced compiler-inserted assert
source-file names — a huge gift in stripped firmware:
- `inputmidi_listener.c` @ `0x08011707`
- `midiobj_backend.c`    @ `0x08014f6b`

Any function that references one of these strings lives in that translation unit. So
the **address ranges around `0x08011xxx` (input listener) and `0x08014xxx` (MIDI object
backend)** are pre-labelled modules for free. We also got the USB descriptor strings,
which name the device's MIDI endpoints:
`Launchkey Mini MK3 MIDI Port`, `… DAW Port`, `… MIDI Int` (the InControl internal
port), `… HID`, `Novation MSD` (mass-storage = firmware-update mode).

## Tracing the path (callers/callees over the corpus)
Cross-referencing the modules with the MIDI status-byte decode sites (grep `firmware.c`
for `& 0xf0` against `0x80/0x90/0xb0/0xe0`) and walking the call graph with
`q.py callers/callees` gave the whole chain:

```
USB OTG_FS  (0x08015xxx, FUN_08015864/08015970 touch OTG_FS regs)
   │
   ▼
midiobj_backend.c  (0x08014xxx)              MIDI transport / stream objects
   │   FUN_0800c238, FUN_0800c2d6  ──────►   two input feeds (USB MIDI vs DAW/InControl)
   ▼
midi_in_router        = FUN_0800c0c6         ★ central parse/dispatch (17 callees);
   │                                            fans out to 12 message-type handlers
   ├─► 12 handlers (FUN_0801179c, _1194c, _11b46, _11c18, _11c7c, _11d26, _11d8e,
   │     _11df2, _11e9a, _11fe4, _120a4, _1215a) — one per MIDI message type
   │     (note-on/off, CC, pitchbend 0xe0-0xe3, etc.)
   ▼
midi_in_publish       = FUN_080116a4         ★ publish event to listeners (all 12 call it)
   │
   ▼
note-state + engine   (0x08016xxx: note allocator / arp)
```

## State we can now read (the "knobs" for musical features)
`midi_in_router` and the handlers keep MIDI state in per-channel × per-note tables,
accessed via `midi_note_state_get`/`set` (`FUN_0800cdcc`/`FUN_0800cdf8`, **27 callers** —
the hot core of MIDI state):
- `g_midi_note_value_ptr` @`0x0801531c` → table indexed `base + (chan&0xf)*0x100 +
  (note&0x7f)*2` = **16 ch × 128 notes × 2 B (14-bit value**, masked `&0x3fff` — velocity/
  pressure/pitchbend value).
- `g_midi_note_state_ptr` @`0x08015320` → `base + (chan&0xf)*0x80 + note` =
  **16 ch × 128 notes × 1 B** on/off + velocity byte.
- `g_note_active_matrix_ptr` @`0x08016c00` → same 16×128 shape in the engine module
  (`FUN_08016b62/b7e`) = which notes are currently held (arp's input set).

The engine *emits* MIDI through note-on builders (`... & 0xf | 0x90`) in
`FUN_0801bbec`, `FUN_0801acf0`, `FUN_08017940` — these are the **MIDI-out** points we'll
tap with a capture script to verify arp/scale edits exactly (no eyeballing).

## Why this matters
- We're now standing at the front door of the musical engine. Arp/scale/chord all read
  the held-note set (`g_note_active_matrix`) and emit via the note-on builders.
- Newly named (in `symbols.tsv`): `midi_in_router`, `midi_in_publish`,
  `midi_note_state_get/set`, and the three note tables. Coverage 18 → 22 functions
  (1.8%), 7.1% → **9.0% of code bytes**.

## Next
1. Read the 12 message-type handlers to label note-on/off/CC/pitchbend precisely, and
   name `FUN_0800c238/c2d6` once we confirm which is USB vs DAW.
2. From `g_note_active_matrix` (the held-note set), follow consumers into the **arp**
   engine (0x08016xxx) — the tempo source + step/pattern tables.
3. With hardware: `scripts/midi_capture.py` on the note-on builders to verify edits.
