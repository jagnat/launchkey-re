# Note 31 — The MIDI input router pipeline (go nuts 5)

**Avenue:** coverage, closing the input loop. Notes 26-29 mapped the control plane from the
`ctrl_in_*` transform stages outward; what fed those stages — `midi_in_router` — was still a
wall of `FUN_`. This round names that backbone.

## "Router" is a misnomer — it's a per-tick pipeline

I expected `midi_in_router` to be a `switch(status & 0xf0)` dispatcher (note-on → handler,
CC → handler, …). It isn't. It's a **fixed-sequence pipeline** run once per input tick:

1. Resolve the source: `route_channel_get(id)` maps a control/route id to a byte whose low
   nibble is the MIDI channel; `channel_route_list_get(chan)` returns that channel's list of
   route ids (0xff-terminated).
2. Walk the route list, calling `control_claimed_any(id)` per entry and counting how many are
   "claimed" by a feature (stored back per-channel).
3. Run the processing stages **in order**, each separated by a tiny `return;` barrier
   (`FUN_0800c166`/`c1f4` — 8/12-byte funcs that decompile to nothing; almost certainly memory
   barriers, deliberately left unnamed per the note-30 nullsub rule). The stages are exactly
   the note-26 family: a value stage, `note_event_process`, pitchbend, realtime,
   `ctrl_in_pot_release`, etc., ending in subscriber fan-outs.

So the picture from notes 26-31 is now whole: **`midi_in_router` (pipeline) → claim/route
resolve → `ctrl_in_*` transform stages → `(class,index)` store → publish fan-out →
`ctrl_out_dispatch` → encode/smooth → `midi_tx`.** One linear flow, end to end.

## `control_claimed_any` and the 5 leaf predicates

`control_claimed_any` (0x0800B91C) is a short-circuit OR over five small predicates, each a
boolean "does this control id belong to feature N?":

- `control_claim_u16`  — per-control u16 table non-zero
- `control_claim_byte` — per-control byte ∈ {not 0, not 1}
- `control_claim_id36` — the specific id 0x36 with a field set
- `control_claim_hi`   — ids 0x80–0xff via a 128-byte table
- `control_claim_id78` — the specific id 0x78 with a flag

The value isn't just five names — it's that these are the **entry points into the `0x0800F_`
module**, a 68-function subsystem that's otherwise opaque. Each predicate reads a distinct
feature table (`DAT_0800f4cc/f048/f690/f22c/f7d8`), so those five tables are the keys to
splitting that module later. `ctrl_feature_write` (0x08011630) is the other door in: it commits
a control value into the same module's buffers (`DAT_0800fa80` + a dirty-bitmap). That's the
designated next coverage target.

## A small structural find: three adjacent publish lists

`midi_in_publish` (note 26) uses a callback list at `0x08011704`. This round turned up two more
fan-out functions using lists at `0x08011700` and `0x080116fc` — three **adjacent** pointers.
That's not a coincidence: it's one structure with three callback-list slots, i.e. a
**multi-phase publish** (the router calls the "flush" one repeatedly between stages and the
"frame" one once at the end). Named `midi_in_publish_flush` / `_frame` by their observed call
pattern (☆ on the phase semantics).

## Bookkeeping

- 16 funcs named (14 pipeline + 2 thunks) → 300/1233 (24.3%), 30.2% bytes.
- MAP: new "MIDI input router pipeline" section + coverage line.
- Honest caveat: most names here are ☆ — the structural roles are clear from data-access
  shapes, but the decompiler lost register args across several stages (the router passes state
  in registers between tail-calls), so exact field offsets are inferred, not read clean.
- Session arc (notes 26-31): 180 → 300 functions (14.6% → 24.3%).
