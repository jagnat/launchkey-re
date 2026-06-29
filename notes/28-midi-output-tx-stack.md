# Note 28 — The MIDI output / TX stack (and the symmetry that closed note 26)

**Avenue:** coverage, bananas round 2. After mapping the *input* side (control-mapping
layer, note 26) and the scale/chord engine (note 27), I took the **output** side — the
note/MIDI emit cluster the MAP had flagged as a capture target.

## The TX stack, bottom to top

```
midi_send / midi_tx_sysex / ctrl_out_encode   (producers)
        |
     midi_tx (0x0800B35C)                       (serializer / router)
        |
   ┌────┴────┐
usb_midi_packet_put      midi_byte_enqueue      (ring-buffer writers)
(0x0800912A, 4-byte)     (0x080090F6, 1-byte)
```

- **`midi_byte_enqueue`** and **`usb_midi_packet_put`** are the primitives: both push into a
  per-port **ring buffer** (`p[0]`=base, `p[1]`=tail, `p[2]`=head, `p[3]`=size mask). One
  pushes a single byte; the other writes a 4-byte USB-MIDI event packet (and first checks
  there's ≥4 bytes of room). Classic lock-free SPSC ring.
- **`midi_tx`** (0x0800B35C) is the **serializer/router**. The port object carries a mode at
  `p[4]`: mode 0 → emit a USB-MIDI packet (`cable<<4 | status>>4` as the packet header);
  nonzero → emit a raw byte stream, computing the message length (1/2/3 bytes) from the status
  byte. It also honors a filter flag at `p[3]` (drop channel messages below 0xf8). `p[5]` is
  the USB cable/jack number.
- **`midi_tx_sysex`** (0x0800B3F0) is the SysEx path — **18 callers**, all the extdata/config
  response builders. It accumulates bytes until `0xf7`, then flushes using the USB-MIDI SysEx
  continuation packet codes (4/5/6/7 = "SysEx ends with 1/2/3 bytes" / "SysEx continues").
  That high fan-in is a good signal this is *the* config-reply transmitter.

## The payoff: `ctrl_out_encode` is the mirror of `ctrl_in_*`

The function that made this cluster worth doing is **`ctrl_out_encode`** (0x08017940). It takes
an internal event whose first byte is the same **virtual class byte** from note 26 and emits
the corresponding wire MIDI. Its switch *is* the class→MIDI-type table:

| class (high nibble) | MIDI output |
|---|---|
| 0 / 0xe / 0xf | note-on/off, poly aftertouch |
| 1 | Control Change |
| 2 | NRPN (CC 0x65/100 MSB/LSB pair) |
| 3 | RPN (CC 99/0x62 pair) |
| 4 | Program Change (0xc0) |
| 5 | Pitch Bend (0xe0) |
| 6 | Channel Pressure (0xd0) |
| specials 0xe0-0xe5, 0xf6-0xf8 | MMC/transport-ish + 14-bit variants |

This **closes the open question from note 26.** There I found that the firmware keeps a generic
`(class, index) -> value` store and namespaces everything by a "class byte", but I couldn't say
what the class numbers *meant*. They mean **MIDI message type**: `ctrl_in_*` decodes
wire-MIDI → (class, index, value), and `ctrl_out_encode` encodes (class, ...) → wire-MIDI.
The control plane is symmetric, and the class byte is the pivot. So a future "route knob X to
the arp" mod is really "make the knob's route carry the arp's class+index" — and now I can see
both ends of that pipe.

## Why I stopped where I did

The arp/voice output wrappers `FUN_08014cd6` / `FUN_08014f20` call `ctrl_out_encode`, and behind
them sits a `0x0801775a..7880` sub-cluster that looks like **velocity/MPE voice processing**
(per-voice 8-byte table at `DAT_08014f64`, MPE-ish 14-bit splits). That's a coherent next pass,
but it's intricate enough to deserve its own focused session rather than rushed low-confidence
names — and it's exactly the kind of thing better validated with the `midi_capture.py` harness
(drive the arp, watch what comes out) than read cold.

## Bookkeeping

- 5 new funcs named (all ★, the TX stack is unambiguous) → 197/1233 (16.0%), 28.1% bytes.
- MAP: new "MIDI output / TX stack" section; coverage line + RX-section row updated.
- Net for the session (notes 26-28): the full MIDI I/O + control plane + scale/chord engine,
  180→197 funcs.
