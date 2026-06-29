# Note 26 — The control-mapping layer (how a knob twist becomes a published value)

**Avenue this session:** pure coverage. The user said "keep mapping the code with
symbols, pick an avenue." I picked the cluster of seven `midi_listener_*` placeholders at
`0x08011xxx` because (a) they were a coherent, bounded family all calling one hub
(`midi_in_publish`), and (b) they sit on the musical-engine input path we keep needing —
so naming them pays off twice.

## What I expected vs what they are

I expected "MIDI message-type handlers" (one per note-on/off/CC/...). Wrong. The thing that
splits incoming MIDI by *status byte* is `midi_in_router`. These seven are one stage *later*:
they are the **control-mapping / value-transform layer**. Renamed `midi_listener_*` →
`ctrl_in_*`.

The giveaway was the shared shape every one of them has:

```c
word = route_table[route];                  // per-route descriptor
if ((word & 0xf0000000) != 0x10000000) return;   // "active" tag in the top nibble
class = (word >> 0x10) & 0xff;              // namespaced control class
index = word & 0xffff;                      // 16-bit slot id
midi_note_state_get(class, index, &val);   // read stored value
... transform val ...
midi_in_publish(route, class, index, val); // fan out to subscribers
```

So the data model is: **each physical/virtual control is a "route".** A route's descriptor
word carries an *active* flag, a *class* byte, and a 16-bit *index*. The class byte namespaces
the value store (`midi_note_state_get/set` is keyed by `(class, index)`, not by raw MIDI
channel/note). That's why earlier the note-state table looked like "16ch×128" — it's actually
a generic per-(class,index) value store that MIDI note state is just one tenant of.

## The hub: publish = subscriber fan-out, not "send MIDI"

`midi_in_publish` @0x080116A4 is tiny and decisive:

```c
for (i = 0; i < cb_count; i++) cb_array[i](route, class, index, val);
```

It walks a registered callback array (`_DAT_08011704`, count at `+0x20`) and calls each.
This nails the architecture as **publish/subscribe**: the `ctrl_in_*` stages are *producers*
that normalize a value and broadcast it; features (arp, LEDs, MIDI-out) register as
*subscribers*. So renaming these "listeners" was itself a misnomer fix — they publish, they
don't listen.

## The transform menu (this is the interesting part)

Each stage handles a different control *class* and applies a different transform. The classes:

- **0xe0–0xe3** — pitchbend/wheel group (`ctrl_in_wheel`, `ctrl_in_wheel_scaled`). 14-bit
  values, `>>9` to fold to 7-bit, or kept 14-bit with the `0x4000` valid-bit.
- **0xf6–0xf8** — a "special/realtime" group (`ctrl_in_special`, `ctrl_in_special_pickup`).
- **top-nibble 0x10–0x60** — the pots/encoders group (`ctrl_in_pot_modes`,
  `ctrl_in_pot_release`, `ctrl_in_pot_press`).

The pot stages read a **mode** from the per-control config (`ctrl_cfg_get` returns a 16-byte
struct; `+0xd & 7` is the mode): **0=fixed, 1=relative, 2=toggle, 6=relative-with-clamp**.
Two mechanisms make these feel "pro":

1. **Soft-takeover / pickup** (`ctrl_soft_pickup` + `ctrl_pickup_gate`). Keeps a per-control
   last-value array + flag bits and *suppresses* output until the physical control passes
   through the stored value — so a knob that's physically at 100% doesn't jump a parameter
   when you switch to a page where that param was at 10%. Classic hardware-controller UX.
2. **Range scaling** (`ctrl_value_scale`): `base ± ((|v-base|+1)*gain >> 16)`, a 16.16
   fixed-point scale-about-a-center using the config's lo/hi range fields (+2/+4).

`ctrl_in_pot_press`/`_release` also maintain an **active-route list** (`DAT_08012304`, count
at +0x34) with find-min eviction when it overflows 16 entries — i.e. a small LRU/priority set
of "currently engaged" controls.

Three enable bitmaps (`ctrl_route_enabled_a/b/c`, 1 bit per route) gate the wheel / special /
pot stages independently, and `route_is_incontrol` tests whether a route is in InControl/DAW
mode (`route<0x78 && mode&0xf000==0x2000`).

## Why this matters for the knob→arp dead end (note 25)

Note 25 concluded physical knobs are output-only standalone: they emit raw pot CCs
(0x1a–0x1c/ch16) that never reach `arp_cc_in_handler`. This layer explains the *mechanism*:
a knob's value only lands on a feature if its **route descriptor's class+index** maps it
there. Standalone, the pots' routes aren't wired to the arp's (class,index); Ableton's
Launchkey script is what reassigns them. So a future standalone knob→arp mod isn't about
hooking the arp CC handler — it's about rewriting a pot route's class/index (or adding a
subscriber that watches the pot class and writes arp config). The missing piece is the
**class-byte → physical-control decode** (which class number = which knob/fader/pad), which
I did not crack this session — that's the next thread if we pursue it.

## Bookkeeping

- 9 new symbols promoted to `re/symbols.tsv`; corpus regenerated (189/1233 = 15.3%, +9).
- MAP.md gets a new "Control-mapping layer" section + a coverage line in Current status.
