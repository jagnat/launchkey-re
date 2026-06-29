# 23 — The arp Controls page: how the UI actually works

This note documents the **arp control page** (hold *Arp* on the device) end-to-end: how a
pad press becomes an arp-config change and an LED update. We needed this to surface the
Euclidean rhythm presets on-device (note 22 left the engine *dormant* — no way to pick
presets 5–10). It turned out the UI is a clean, regular little state machine, and the
write path lands **exactly** on the function we already hijacked for Euclidean, so the
remaining mod is tiny. This note is the "why it's shaped this way," with addresses.

## The two-layer split (the thing to internalise)

There are **two separate structs** and the code is deliberately partitioned:

- **UI state struct** — base in `g_arp_state_ptr` (`0x2000e628`). Holds *what the page is
  showing*: `+0` = arp-on flag, `+2` = "page held/latched" flag, **`+0xc` = active group
  (0–3)**. This is pure presentation state.
- **Arp config struct** — pointer `DAT_080148c0` (the live arp params at `0x20001fac`):
  `+1` mode, `+2` octave, **`+3` rhythm selector**, etc. This is what the *engine* reads.

The `0x08013xxx` cluster (render + input) **never writes the config struct** — confirmed
by `q.py xref 0x20001fac` (only the `0x08014xxx` engine cluster writes it). The UI reaches
the config only by calling a **bridge** in the engine cluster. That separation is why
"change a rhythm" isn't a single function — it's UI → bridge → engine.

## Input path — `arp_control_handler` @ `0x0801391C`

`control_dispatch` (`0x0800C72C`) fans every control event out to ~22 handlers;
`arp_control_handler` is the arp page's. With the page active (`*g_arp_state_ptr != 0`) it
routes by pad index `param_1`:

| pad index | meaning | action |
|---|---|---|
| `0..3` | **top row = group select** | `*(g_arp_state_ptr+0xc) = param_1` (pad 3 gated by a flag) |
| `4`, `5` | two page toggles (latch etc.) | `arp_ui_refresh` / branch |
| `8..0xf` | **bottom row = value**, dispatched by *current group* | see below |

Bottom-row dispatch reads the active group (`g_arp_state_ptr+0xc`) and calls a
per-group value handler:

| group | colour | meaning | value handler | cells |
|---|---|---|---|---|
| 0 | purple | **Mode/Type** | `arp_3770` | 7 (pads 8–0xe) |
| 1 | orange | **Rate** | `arp_37be` / `arp_apply_rate` | rate + triplet |
| 2 | blue | **Octave** | `arp_set_mode` | 5 (pads 8–0xc) |
| 3 | yellow | **Rhythm** | **`arp_387c`** | 5 (pads 8–0xc) |

(The 4-group count is independently confirmed by the colour table — see render below.)

### The value handlers are range-guards + a shared bridge

Every value handler has the **same shape**. `arp_3770` (Mode) is the clearest template:

```c
arp_3872();                       // FUN_0801480e: fetch pressed pad -> value in r4
*(g_arp_state_ptr+0xc) = 0;       // keep group selected
switch (value) {                  // <-- THE RANGE GUARD
  case 0: local = 0; break;
  ...
  case 6: local = 6; break;       // Mode accepts 0..6 (7 modes)
  default: return;                // out of range -> ignore the press
}
FUN_08014812(&local);             // arp_386a wraps this: APPLY
```

`arp_387c` (Rhythm) is byte-for-byte the same idea but the `switch` only enumerates
**cases 0,1,2,3,4** — the five stock rhythms (O / OXO / OXXO / Random / Deviate). Press a
pad whose value is ≥5 and it hits `default` and is silently dropped. **That switch is the
only thing stopping us from selecting Euclidean presets.** It is the exact UI analogue of
the CC 0x5b clamp (`0..4`) at `FUN_0801aaf0`.

## The bridge — `FUN_08014812` @ `0x08014812` (why this is the punchline)

`arp_386a` → `FUN_08014812(newvalue)` is where UI crosses into the engine:

```c
FUN_080143f8(config, newvalue);   // write the new selector into arp config (0x20001fac)
FUN_080170f8(config, ...);        // recompute per-step timing
FUN_080175b0(config, ...);        // *** rhythm_decode — OUR Euclidean detour ***
FUN_08016d7c(config);             // refresh
...                               // forward state out
```

It calls **`FUN_080175b0` = `rhythm_decode`** — the function note 22 detoured to add the
Euclidean masks. So the entire on-device pick path already terminates in our code:

```
press (Rhythm group) -> arp_control_handler -> arp_387c
   -> [switch guard 0..4]          <- widen this
   -> arp_386a -> FUN_08014812
        -> FUN_080143f8  (config[+3] = value)
        -> rhythm_decode (DETOURED) -> Euclidean mask for value 5..10
```

The CC 0x5b path (`FUN_0801aaf0`) funnels through the *same* `FUN_08014812`, so both the
knob/CC route and the pad route share one apply. Nice and orthogonal.

## Render path — `arp_page_render` @ `0x08013508`

Lights all 16 pads for the page. Skeleton:

- `FUN_080148b0()` == arp-on? If off, dim everything; else draw.
- Pad `0x15` (the Arp button LED) lit white; `arp_3874()` reloads the UI mirror of config
  into the stack locals the renderer reads (mode/octave/rhythm/toggles).
- **Group selector LEDs:** `led_set_color(group, DAT_08013b00[group])`. `DAT_08013b00` is a
  **4-entry colour table** — `{0x7f00ff purple, 0xff3f00 orange, 0x1f3fff blue,
  0xffff00 yellow}` — after index 3 the bytes are code, proving exactly 4 groups.
- **Bottom row:** `switch(group)` renders that group's value cells. Each branch lights the
  unselected cells dim and the selected one bright, using the per-group colour constants:

| group | dim cells | active cell | active colour |
|---|---|---|---|
| 0 Mode | `DAT_08013ad4` `0f001f` | `switch` value→pad 8..0xe | `DAT_08013ad8` `7f00ff` |
| 1 Rate | `DAT_08013adc` `1f0700` | via `arp_rate_get` | `DAT_08013ae0` `ff3f00` |
| 2 Octave | `DAT_08013ae4` `07071f` | `(val-1)≤4`→pad 8..0xc | `DAT_08013ae8` `1f3fff` |
| 3 **Rhythm** | `DAT_08013aec` `1f1f00` | `switch` value→pad 8..0xc | `DAT_08013af0` `ffff00` |

So the Rhythm branch currently paints **only pads 8–0xc** (values 0–4); pads **0xd, 0xe,
0xf are unused** in this group. That's our free space.

> Aside: `arp_mode_select` @ `0x08013B34` operates a *different* struct (`DAT_08013e00` =
> `0x2000e648`, not `g_arp_state_ptr`). It is **not** the arp-rhythm page input — earlier
> map notes guessed it was. It looks like a sibling page (scale/fixed-chord?) and is left
> for a later note. The real arp page input is `arp_control_handler`, documented above.

## The other entry point — arp knobs / incoming CC (`FUN_0801aaf0` @ `0x0801AAF0`)

The device's **arp knobs send channel-0 CCs** (`0xB0`), handled here. Each CC writes one
field of a staging struct, then the **same `FUN_08014812` bridge** the pads use applies it —
so knobs and pads converge on one apply (and one `rhythm_decode`). The full arp CC map:

| CC | param | handling | config |
|---|---|---|---|
| `0x55` | Mode | switch 0–6 | +1 |
| `0x56` | Rate | 1–7 → divisor {0x10..2} | +0 |
| `0x57` | Octave | clamp ≤3, +1 | +2 |
| `0x58` | Latch | value≠0 | +4 |
| `0x59` | Gate | clamp 0–99 → `(v<<7)/99` | +7 |
| `0x5a` | **Mutate** | clamp `[0x22,0x5e]`, `<<1` | +6 |
| `0x5b` | **Rhythm** | switch 0–4 else 0 | +3 |
| `0x5d` | **Deviate** | passthrough | +9 |

On the Mini MK3 the arp **knobs drive Mutate (`0x5a`) and Deviate (`0x5d`)** — confirmed by
the user against the physical unit. **No knob is bound to Rhythm**, so on-device Rhythm
selection is the **pad row** (`arp_387c`); CC `0x5b` is Rhythm's external/DAW entry. The
`0x5b` clamp (`0..4`) is the exact CC twin of the `arp_387c` pad guard — widen both to make
Euclidean reachable from both surfaces. (A deliberate alternative: rebind a knob to Rhythm
so it sweeps all presets 0..10 — costs that knob's current Mutate/Deviate function.)

## What this unlocks for the Euclidean UI (note 22 → ship)

The on-device mod is now two small, well-understood edits — **no new render branch, no new
group**, just widening the existing Rhythm group:

1. **`arp_387c` guard** — extend the `switch` so values 5..N are accepted (fall through to
   `arp_386a`/apply) instead of hitting `default`. Currently 0–4 → make it 0–7 (3 new) or
   wider if we use more pads.
2. **`arp_page_render` Rhythm branch** — paint pads `0xd..0xf` (and however many) as
   Euclidean cells, and light the active one when `value ≥ 5`.

**Open design choice (for the build step):** the Rhythm row has only **3 free pads**
(`0xd/0xe/0xf`), but we built **6** Euclidean presets (E4,5,6,7,9,11). Options:
- (a) surface **3** presets on-device now (e.g. E4/E5/E7), keep all 6 reachable via CC 0x5b
  (also widen that clamp) — lowest risk, ships immediately;
- (b) a **page toggle** (one of the pad-4/5 toggles, or a long-press) to swap the Rhythm
  row between "stock 5" and "euclid 6" banks — all 6 on-device, more code;
- (c) a **whole new group** (needs a 5th colour-table entry + render branch + top-row pad) —
  most work, cleanest long-term, and good practice for the "replace stock UI" goal.

Also need to confirm the value-fetch (`FUN_0801480e`/`FUN_080143f8`) returns `pad-8` for the
full `8..0xf` range without clamping at 6 (Mode only exercises up to pad 0xe). Cheap to
check on hardware: widen the guard, press pad 0xf, watch the gap signature.

## Quick reference (addresses)

| symbol | addr | role |
|---|---|---|
| `control_dispatch` | `0x0800C72C` | control-event hub → all feature handlers |
| `arp_control_handler` | `0x0801391C` | arp page input router (top row=group, bottom=value) |
| `arp_3770` | `0x08013770` | Mode value handler (guard 0..6) — template |
| `arp_37be` | `0x080137BE` | Rate value handler |
| `arp_set_mode` | `0x08013844` | Octave value handler |
| **`arp_387c`** | **`0x0801387C`** | **Rhythm value handler (guard 0..4) — widen here** |
| `arp_386a` | `0x0801386A` | wraps `FUN_08014812` (apply) |
| `arp_3872`/`arp_3874` | `0x08013872`/`0x08013874` | wrap `FUN_0801480e` (fetch pressed value) |
| `FUN_08014812` | `0x08014812` | **apply bridge**: write config + call rhythm_decode |
| `FUN_080143f8` | `0x080143F8` | write a value into the arp config struct |
| `arp_page_render` | `0x08013508` | draw 16 pads; `DAT_08013b00`=4 group colours |
| `FUN_0801aaf0` | `0x0801AAF0` | CC 0x55–0x5b writer (0x5b=Rhythm, clamp 0..4) — same apply |
| UI state struct | `0x2000e628` | `+0` on, `+2` held, `+0xc` active group |
| arp config struct | `0x20001fac` | `+1` mode, `+2` octave, `+3` rhythm sel |
