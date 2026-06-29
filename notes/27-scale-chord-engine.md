# Note 27 — The scale/chord engine (and a recurring "observable config" idiom)

**Avenue:** coverage, "go bananas" edition. After the control-mapping layer (note 26) I
took the `0x08016xxx` cluster — it sits right next to the arp engine and was full of
`scale_*` placeholders, so it was both adjacent and musically central.

## The payoff: three modules, one shape

The cluster turned out to be **three separate config modules**, and the strings nailed it
down hard — `scale.c`, `layout_channel.c` (both via `assert_failed` `__FILE__` strings), plus
a third unnamed "chord/scale-set" module, with UI labels elsewhere in flash: "Scale On",
"Scale Set", "Scale Chord", "Fixed Chord", "User Chord", "Chord Pickup", "Delete Chord!".

What made naming fast is that all three share one **idiom** I now recognize on sight:

```c
// register: append a callback to the object's observer array
observer_add(cb) { obj->cb[obj->count++] = cb; }   // asserts count < 8

// mutate: change a field, and if it actually changed, notify everyone
field_set(i, v) { if (obj->field[i] != v) { obj->field[i] = v;
                    for (k=0; k<obj->count; k++) obj->cb[k](); } }
```

So each config object is an **observable**: pages/LED renderers subscribe via `*_observer_add`,
and any mutation fans out a "config changed, re-read me" pulse. That's why these modules have
no direct coupling to the UI — they just publish change events. (Same architectural flavor as
`midi_in_publish` from note 26; this firmware leans hard on observer/callback arrays.)

Concretely:
- **layout_channel** (`g_layout_cfg_ptr`@0x08016974): 3 per-zone MIDI channel/mode nibbles.
  `layout_mode_get` is the hot reader (10 callers).
- **scale** (`g_scale_cfg_ptr`@0x080169DC): `+0` enable, `+4..+0xf` = a 12-entry **interval
  map** (one offset per pitch-class).
- **chord/scale-set** (`g_chord_cfg_obj_ptr`@0x08016D58): a 13-byte per-degree chord table
  (`g_chord_degree_table_ptr`), a 128-bit scale-membership bitmap (`g_scale_noteset_ptr`),
  and a 9×4-char name table (`g_chord_name_table_ptr`).

## The one function that matters most: `scale_quantize_note` (0x080169B6)

```c
if (note < 0x80 && (force || scale_enabled)) {
    pc = note % 12;                 // fold to pitch class
    note += interval_map[pc];       // snap into the scale
}
return note;
```

Tiny, but it's the **seam where "scale mode" actually bends pitch** — and crucially its
callers include `arp_step_emit`. That ties two clusters together: the arp engine I'd already
mapped doesn't quantize itself; it leans on `scale.c`. `held_note_apply_scale` (0x08016E4A,
called by `arp_held_note_add`) is the other arp↔scale bridge, re-quantizing held notes.

## The editor: `chord_edit_handler` (0x0801ACF0)

This is the "Scale Chord / User Chord" page logic. It parses incoming **notes (0x90/0x80)**
and **CCs (0xb0)** into the chord/scale config (`g_chord_edit_cfg_ptr`@0x0801AE24). The CC's
high-nibble selects what you're editing — degree assignment vs scale-note toggle vs slot —
routing into `chord_degree_set` / `scale_note_set` / the degree slots. It's gated off while
`arp_get_state()==1`, and `chord_slot_release` (0x0801ACB0) flushes queued note-offs (these
use the generic value store under class bytes 0xf7/0xf8 — the same `(class,index)` store from
note 26, confirming that store is a shared scratchpad, not just MIDI note state).

## Bookkeeping & next lead

- 10 placeholder upgrades + 3 new funcs + 9 data pointers → 192/1233 (15.6%), 27.0% bytes.
- **Next coverage lead:** the `0x08010xxx` page-UI cluster — these are the *subscribers* to
  the three observables. Caveat: it's mostly 2–4 byte vtable/stub thunks (low value to name
  individually) with a few fat page handlers (`FUN_0801024e` is 490 B). Worth a targeted pass
  on the big ones rather than a blanket sweep.
