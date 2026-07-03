# USB-MIDI RX path, TX stack, control-smoothing engine

Confidence: ★=verified, ☆=strong inference, ?=guess.

## USB-MIDI RX path (note 19) — the musical-engine gateway
Source modules (from kept `__FILE__` strings): `inputmidi_listener.c`@0x08011xxx,
`midiobj_backend.c`@0x08014xxx. USB ports: MIDI Port / DAW Port / "MIDI Int" (InControl).
| symbol | addr | role |
|---|---|---|
| `midi_in_router` | `0x0800C0C6` | ★ parse+dispatch incoming MIDI → 12 type handlers (17 callees); pipeline detail in input.md |
| `midi_in_publish` | `0x080116A4` | ★ fan-out event to listeners (all 12 handlers call it) |
| `midi_note_state_get`/`set` | `0x0800CDCC`/`0x0800CDF8` | ★ read/write MIDI note state (27 callers) |
| `g_midi_note_value_ptr` | `0x0801531C` | ★ 16ch×128×2B 14-bit value table (`&0x3fff`) |
| `g_midi_note_state_ptr` | `0x08015320` | ★ 16ch×128×1B note on/off+vel |
| 12 handlers | `FUN_0801179c…0801215a` | ? one per message type (note-on/off/CC/pitchbend) — not yet split |
| `FUN_0800C238`/`C2D6` | — | ☆ the two input feeds (USB vs DAW) |
USB stack: `usb_otg_fs_isr`@`0x08018184` (1298 B, 24 callees) — USB **is** interrupt-driven;
device stack spans ~0x08015800-0x08019xxx (interleaved with confstore/extdata .c ranges).

## MIDI output / TX stack — mirror of the RX/ctrl-in path
| symbol | addr | role | conf |
|---|---|---|---|
| `midi_send` | `0x0800B3D0` | high-level note/CC/etc send → `midi_tx` | ★ |
| `midi_tx` | `0x0800B35C` | serializer: per-port obj (`p[0]`=ringbuf,`p[3]`=filter,`p[4]`=mode,`p[5]`=cable); mode0→USB-MIDI packet, else byte-stream (len 1/2/3 from status) | ★ |
| `midi_tx_sysex` | `0x0800B3F0` | **SysEx TX** (18 callers): frames `0xf0..0xf7`, emits USB-MIDI SysEx packet codes 4-7; used by all extdata/config SysEx response builders | ★ |
| `usb_midi_packet_put` | `0x0800912A` | push a 4-byte USB-MIDI event packet into the TX ringbuf (checks ≥4 free) | ★ |
| `midi_byte_enqueue` | `0x080090F6` | push 1 byte into a TX ringbuf (head `p[2]`, tail `p[1]`, mask `p[3]`) | ★ |
| `ctrl_out_encode` | `0x08017940` | **output mirror of `ctrl_in_*`**: virtual class byte → MIDI status. High-nibble: 1=CC, 2=NRPN (0x65/100), 3=RPN (99/0x62), 4=PC(0xc0), 5=pitchbend(0xe0), 6=chan-pressure(0xd0), 0/0xe/0xf=note/poly-AT; specials 0xe0-0xe5/0xf6-0xf8 | ★ |
| `midi_out_forward` | `0x0801BBEC` | forward note/CC/PC out + update note-state store | ☆ |
| `chord_edit_handler` | `0x0801ACF0` | ☆ see scale-chord.md |
The control abstraction is symmetric: `ctrl_in_*` decode wire-MIDI→(class,index,value),
`ctrl_out_encode` encodes (class,…)→wire-MIDI — this answered note 26's open "class byte →
MIDI type" question.

## Control-smoothing / thinning engine — `ctrl_smooth_emit`
Continuous 14-bit controls (pitchbend/CC, virtual classes 0xe1/0xe3-0xe5/0xf7) don't emit raw —
they go through a **send-on-change + TX-throttle** engine so a fast knob sweep can't flood the
MIDI queue. State = a per-group **active-control tracking list** (3 groups × 32 slots):
| symbol | addr | role |
|---|---|---|
| `g_ctrl_track_count` | `0x08017874` | per-group active count (3 bytes) |
| `g_ctrl_track_keys` | `0x08017878` | 3×32×u32, key = `class<<16 \| index` |
| `g_ctrl_track_values` | `0x0801787C` | 3×32×u16, last-sent value per active control |
| `ctrl_track_find/add/remove` | `0x08017734`/`775A`/`77F4` | slot mgmt (find by key; add w/ cap 32; swap-remove) |
| `ctrl_track_value_set/get` | `0x0801782C`/`784E` | read/write the tracked last value |
| `ctrl_emit_gated` | `0x08017880` | emit a step via `ctrl_out_encode` only if TX load + an LFSR gate (`DAT_080178d8`) + change threshold allow |
| `ctrl_smooth_emit` | `0x08014CD6` | the engine: `delta=\|new-old\|`; branches on `tx_queue_load` — high load → throttle/drop, low → track+emit (`DAT_08014f64`=per-control port-obj table ×8) |
| `ctrl_out_dispatch` | `0x08014DF8` | publish-subscriber: per destination, route by class → smooth path for continuous, direct `ctrl_out_encode` for discrete (callers incl. `midi_note_state_set`) |
| `ctrl_out_flush` | `0x08014E90` | sibling that `ctrl_track_remove`s each destination (teardown / value reset) |
| `tx_queue_load` | `0x0800B502` | TX ring occupancy (`ringbuf_used`) scaled → throttle level |
| `tx_free_headroom` | `0x0800B4E2` | TX ring free (`ringbuf_free`) scaled minus safety floor |
| `ringbuf_used`/`ringbuf_free` | `0x080091C2`/`91D0` | generic SPSC ring fill/free (`(head-tail)&mask` / `(tail-head-1)&mask`) |
**Leads:** the `0x0801775a` register-arg loss means group-id/count fields are inferred; the
per-control port-obj table `DAT_08014f64` and the `0x08014ef4/f02/f10` iterator helpers are
still `FUN_`. Best confirmed live with `midi_capture.py` (sweep a 14-bit CC fast, watch
thinning).
**Observer idiom (recurring):** config objects expose `*_observer_add(cb)` storing a fn-ptr in
an array; mutators loop `for i<count: cb[i]()`. The page-UI modules in `0x08010xxx` are the
subscribers (mostly tiny vtable/stub thunks + a few large page handlers like `FUN_0801024e`
490B).
