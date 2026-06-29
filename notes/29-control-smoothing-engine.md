# Note 29 — The control-smoothing / thinning engine (bananas round 3)

**Avenue:** coverage. The teed-up lead from note 28 was the arp/voice output sub-cluster
(`FUN_08014cd6` + `0x0801775a..7880`) I'd guessed was "velocity/MPE voice processing." It's
adjacent and uses `ctrl_out_encode`, so it was the natural next bite.

## What it actually is: send-on-change with TX backpressure

My "voice/MPE" guess was half-right in shape (a per-slot table) but wrong in purpose. This is
a **continuous-controller smoothing/thinning engine**. The problem it solves: a fast pitchbend
or 14-bit CC sweep generates values far faster than a 31.25 kbaud MIDI stream (or even USB) can
carry. So instead of emitting every change, the firmware:

1. Tracks each **active continuous control** in a small list keyed by `class<<16 | index`
   (the same class/index identity from notes 26/28), storing the **last-sent value**.
2. On a new value, computes `delta = |new - last|`.
3. Looks at **TX queue backpressure** (`tx_queue_load` = scaled `ringbuf_used`; `tx_free_headroom`
   = scaled `ringbuf_free` minus a safety floor) and decides: queue busy → throttle/skip;
   queue has room and the value moved enough → emit a step and update the tracked value.
4. An LFSR gate (`DAT_080178d8`, the `... *2 ^ 0xdb` step in `ctrl_emit_gated`) adds a little
   dither so thinning doesn't lock onto a fixed grid.

So the "32 slots × 3 groups" table (`g_ctrl_track_keys`/`_values`/`_count`) is an **active-
control set**, not a voice allocator. Each entry = one continuous control currently being
smoothed, with its last transmitted value.

## How I pinned it down

The decompiler lost a lot of register args here (`unaff_r5/r6/r7` everywhere — these funcs are
reached via tail-calls that keep state in registers), so I leaned on the **data-access shapes**
instead of the C:

- `ringbuf_used` = `(head - tail) & mask`, `ringbuf_free` = `(tail - head - 1) & mask` —
  textbook SPSC ring math, and they feed the two `tx_*` scalers. That fixed "this is about
  queue capacity," which is the whole point of thinning.
- `ctrl_track_find` linear-scans `g_ctrl_track_keys[group]` for `param_3 | param_2<<16` — the
  key is `(index, class)`, tying it to the control-plane identity from note 26.
- The dispatcher `ctrl_out_dispatch` (0x08014DF8) routes by class byte: **continuous** classes
  (0xe1, 0xe3-0xe5, 0xf7) → `ctrl_smooth_emit`; **discrete** ones (0xe0, 0xe2) → direct
  `ctrl_out_encode`. That class split is the clincher: only the continuous ones get smoothed.
  And `ctrl_out_dispatch` is itself a `midi_in_publish` subscriber (caller list includes
  `midi_note_state_set`), so this sits right on the publish fan-out from note 26.

## The shape of the whole control plane (notes 26 → 29)

It now reads end to end:

```
wire MIDI in ─ ctrl_in_* (decode, scale, soft-pickup) ─→ (class,index) value store
                                                              │  midi_in_publish fan-out
                                                              ▼
                                                     ctrl_out_dispatch
                                              continuous │           │ discrete
                                                         ▼           ▼
                                              ctrl_smooth_emit   ctrl_out_encode
                                              (track + throttle)      │
                                                         └────────────┴─→ midi_tx ─→ ring ─→ wire
```

One coherent abstraction, symmetric in/out, with the `(class,index)` pair as the through-line
and a backpressure-aware thinner on the continuous path.

## Bookkeeping & next lead

- 13 funcs + 3 data named → 210/1233 (17.0%), 29.1% bytes.
- **Caveat for future me:** because of the register-arg loss, the group-id and count-field
  offsets in `ctrl_track_*` are inferred from access patterns, not read off clean C — solid but
  not gospel (☆). The per-control port-obj table `DAT_08014f64` and the `0x08014ef4/f02/f10`
  iterator helpers are still `FUN_`.
- This engine is a prime `midi_capture.py` target: sweep a 14-bit CC fast and watch the output
  thin out under load — would upgrade the whole section from ☆ to ★.
