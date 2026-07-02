# Note 34 — On-device Euclidean control: pads = k, held-Arp Deviate knob = n

This is the milestone where the Euclidean arp became **fully controllable on the device,
standalone** — no DAW, no host. Two surfaces: the **Rhythm pads** set density (k) and the
**Deviate knob** sets pattern length (n). Getting here corrected a long-standing wrong belief.

## The wrong turn we were stuck in

Note 25 concluded the physical knobs were a **dead end**: turn a knob standalone and it emits
only a generic pot CC (0x15–0x1c on ch16); it never reaches the arp. We chased this hard this
session — hooked `control_value_emit` (first-touch pot emit) and `FUN_0800f204` (continuous pot
emit), guessing the 8 pots sat at internal indices 0..7. Every HW test: knobs did nothing to the
arp. We even started reverse-engineering `key_event_scan`'s per-id control-type table to find the
"real" pot index.

All of that was solving the wrong problem.

## The manual settled it in one sentence

User guide **page 20, "Arpeggiator Rotary Knobs":** *"When you hold the Arp button the rotary
knobs can transform your arpeggios"* — Tempo / Swing / Gate / **Mutate** / **Deviate**.

The knobs route to arp params **only while the Arp button is physically HELD.** Every "zero
effect" test — note 25's and this session's — turned the knobs **without holding Arp**, so they
did exactly what the manual says they do otherwise: emit generic pot CCs. The routing we wanted
was in the stock firmware the whole time, behind a modifier we never pressed.

**Lesson: read the user manual before reverse-engineering the input path.** A black-box behaviour
question ("do the knobs reach the arp?") is often answered by the product's own docs faster than
by the disassembler. The `key_event_scan` / pot-index dig was real work that the manual made moot.

## Confirming it (no reflash)

On the *current* firmware we set Arp Rhythm = **Deviate** (stock), then **held Arp and turned the
Deviate knob**. `midi_capture.py arp` showed the gaps fan out to a rich set of clean multiples of
6 (6/12/18/24/30/36/48) — the Deviate rest pattern changing live. Proof the held-Arp knob writes
`cfg[9]` standalone. (Monitoring the DAW port during this showed **no CC** emitted — held-Arp knob
input is routed internally to arp config, not sent out. So the write is invisible to MIDI; only
the arp pattern reveals it.)

## The design that keeps the pads AND adds the knob

The euclid engine (`rhythm_decode.s`) now reads BOTH surfaces for cfg[3]∈5..10:

- **k = cfg[3] - 1** — set by the Rhythm PADS. `arp-rhythm-guard-widen` widened
  `arp_rhythm_select`'s guard 0..4→0..10 (note 33-era work), so the free pads 0xd/0xe/0xf write
  cfg[3]=5/6/7. Pads 0xd/0xe/0xf → E(4/5/6, n).
- **n = 16 - (cfg[9] >> 3)** — set by the held-Arp Deviate knob (cfg[9]).

The key trick that satisfies "don't break the pads": **cfg[9]=0 (knob untouched) → n=16**, so the
pads alone still produce exactly the E(k,16) they did before the change. The knob is purely
*additive* — and because it can only ever change n, it literally cannot break the pad path even if
the routing had turned out to be gated. (It wasn't: verified the Deviate knob writes cfg[9] even in
euclid rhythm, not only in stock Deviate rhythm — the manual's "after selecting Deviate rhythm" is
about audibility, not about when the write happens.)

## HW validation

- Pads: pad 0xd → E(4,16) measured as uniform 24-clock gaps @1/16 (12-clock @1/32 — the arp Rate
  differs between takes; the euclid math is rate-independent and matched every time).
- Deviate knob (Arp held), euclid k=4: sweeping the knob moved the gap histogram off the uniform
  baseline into E(4,n<16) distributions (12/18/24/30/36) and held stable when the knob was steady.

## Dead ends removed

`mods/asm/knob_arp_hook.s` and `knob_f204_hook.s` (the pot-scan detours) are deleted — superseded
by the held-Arp routing. Their story lives here and in git history.

## Next

Mutate knob → **rotation** (rot), the 3rd euclid parameter, via the same held-Arp mechanism
(Mutate writes cfg[6]); then the Pitch/Octave tracks off the same `euclid_compute` primitive.
See [[euclidean-arp-feature]] and [[launchkey-mini-arp-knobs]].
