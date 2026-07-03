# Scale / Chord engine — `0x08016xxx` + editor `0x0801ACF0`

Confidence: ★=verified, ☆=strong inference, ?=guess.
Strings confirm the feature ("Scale On/Set", "Scale Chord", "Fixed Chord", "User Chord",
"Chord Pickup"). **Three observable-config objects**, each an observer-pattern struct
(callback array + count; mutators notify all observers on change), one per `.c` module:
| module / obj | file | obj-ptr | API | notes |
|---|---|---|---|---|
| **layout_channel** | `layout_channel.c` | `g_layout_cfg_ptr`@`0x08016974` | `layout_observer_add`@6908, `layout_channel_set`@692C (3 ch bytes, nibble), `layout_mode_get`@695C | per-zone MIDI channel/mode (3 entries, `&0xf`); observers @+4, count @+0x24 |
| **scale** | `scale.c` | `g_scale_cfg_ptr`@`0x080169DC` | `scale_observer_add`@698C, `scale_setting_get`@69B0 (+0x10 ?), **`scale_quantize_note`@69B6**, `scale_def_lookup`@69E8 | obj: +0 enable, +4..+0xf = 12-entry interval map, observers @+0x14, count @+0x34 |
| **chord/scale-set** | (chord_scale) | `g_chord_cfg_obj_ptr`@`0x08016D58` | `chord_name_set`@6C7A, `chord_degree_set`@6CB4, **`chord_degree_lookup`@6CC8**, `scale_note_set`@6D10, `scale_contains_note`@6D3E | `g_chord_name_table_ptr`@6D5C (9×4-char), `g_chord_degree_table_ptr`@6D60 (13 bytes, per-degree chord), `g_scale_noteset_ptr`@6D64 (128-bit scale membership) |

**`scale_quantize_note`@0x080169B6 ★** = the quantizer:
`if note<0x80 && (force||enabled){ pc=note%12; note += interval_map[pc]; }`. Called by
**`arp_step_emit`** and the note-out builders → scale snaps both arp and live notes.
**`chord_degree_lookup`@0x08016CC8** decodes a `g_chord_degree_table_ptr[degree]` byte:
`(b>>4)&3`=type {0=interval via `DAT_08016d68`, 2=interval via `DAT_08016d6c`, else
0x8000=none}, `b&0xf`=value → returns chord interval (16.16 hi).
**`chord_edit_handler`@0x0801ACF0 ☆** = the Scale-Chord/User-Chord **editor**: parses
note(0x90/0x80) + CC(0xb0) into the chord/scale config (`g_chord_edit_cfg_ptr`@`0x0801AE24`);
CC sub-nibble routes to `chord_degree_set`/`scale_note_set`/degree slots;
`chord_slot_release`@0x0801ACB0 issues queued note-offs (state class 0xf7). Gated off when
`arp_get_state()==1`.
**`held_note_apply_scale`@0x08016E4A** = arp-input seam: re-quantizes held notes via
`scale_quantize_note` (caller `arp_held_note_add`).
