# 35 — The publish seam: discrete input ids without a soldering iron (+ the roadmap decision)

## Where we stood

Note 34 left the custom-page project in a frustrating spot. Rendering was solved —
we own the whole 16-pad grid from `main_task_tick`'s empty slot — but input was
blocked. The pad-id scope diagnostic (hooking `control_dispatch`'s call into
`arp_control_handler`) proved that `param_1` at that layer is *not* the pad id;
the real id rides in r4, set somewhere inside the router, invisible to a blind
hook. The two ways forward both looked expensive: solder a UART for printf
debugging, or give up on pads and use a known button id.

## The direction question

With a list of feature ideas on the table (menu layers, looper, note-bounce,
generative engine, "just rewrite it all in C"), the useful observation is that
**almost all of them are the same feature underneath**: a way to latch a custom
mode in and out, pad/knob input we own while it's latched, and rendering we own.
Rendering: done. So the page/menu foundation isn't one option among six — it's
the prerequisite for four of them. That settled the ordering:

1. page/menu foundation (gate + input),
2. Euclid finished *as the first app on it* (live pattern view, knobs = k/n/rot),
3. bounce + generative modes (new generator primitives on the same platform),
4. looper last (needs timing capture + the most RAM).

Full-custom C firmware was rejected — reimplementing USB, the matrix scan, and
config storage with no SWD debugger is a rewrite of everything that already
works, with none of the bootloader's safety net left if we get it wrong. The
middle path gets most of the benefit: keep stock as the "OS", but author the
big mod payloads in **C** (arm-none-eabi-gcc → Thumb, linked into the flash
tail) instead of hand assembly. The menu system will be the first C payload;
`arm-none-eabi-gcc` 14.3 is already on the machine.

## The insight: tap the *publisher*, not the *router*

The input dead end came from hooking too high in the stack — the arp page
router receives pre-cooked events whose pad identity is register plumbing by
then. But note 33 had already mapped the layer *below*: the control-surface
scanner. Every physical control — pads and keys (`control_velocity_scan`),
pots (`pot_scan`, ids |0x80), the pitch strip — funnels its conditioned events
through one function: `control_value_emit` @ `0x0800F840`.

Ghidra's decompile of it was useless (`control_value_emit(void)` calling an
"empty" helper), which is probably why it hadn't clicked earlier. The trick,
same as the `FUN_0800bc78` case in the render work: **when a tiny helper
decompiles as empty, read its bytes.** `FUN_0800f878` is pure register
shuffling — `add r2, r7, r6, lsl #2; mov r1, r5; ldr r3, [r2, #4]; mov r0, r4;
bx lr` — invisible to the decompiler, but it *is* the calling convention,
written down:

- `control_value_emit(r0 = control id, r1 = conditioned value)`
- subscriber table @ `0x2000E3B0`: count byte at +0, callback ptrs at +4+i*4,
  room for 8 (the next table starts 0x24 bytes later)
- each subscriber is called as `cb(id, value)`
- three sibling fan-outs with identical shape: `0x2000E3D4`, `0x2000E3F8`
  (= `control_value_release`, id only), `0x2000E41C`

`pot_scan`'s decompile confirms the arg order from the caller side:
`control_value_emit(idx | 0x80, value)`.

This one seam is the input backbone for everything planned: the page toggle,
in-page pad input, *and* standalone knob→arp (the old "fork c") — all without
opening the unit. The UART option is dead weight now.

## The new diagnostic: ctlscope

`mods/asm/emit_tap.s` is a prologue detour on `control_value_emit`: store r0
(the id) to the debug byte `0x2000DD37`, replay the two displaced entry
instructions, resume at `0x0800F844` (r2/r3 are provably dead there). The
render half is the same bottom-row binary readout as before, but un-gated —
it must work at standalone idle, because that's where a page toggle lives.
Press any pad/key/knob → its id appears in blue binary on pads 8–0xf.

One flash of this build answers the question the whole project has been
circling: *what are the pad ids?* Then the gate mod can watch for a specific
control (or combo) and flip a page flag.

## Toolchain bug of the day

`classify_stubs.py --apply` wrote new rows with bare hex addresses
(`0800effc`) because that's how `firmware.c` headers spell them.
`ImportSymbols.java` parses the address column with Java's `Long.decode()`,
which treats a leading `0` as *octal* — `8` isn't an octal digit, the parse
throws, the row is silently skipped, and `ExportCorpus` then rewrites
`symbols.tsv` from the Ghidra DB, *deleting* the rows that never imported.
Names vanished on the round-trip with `miss=0` reported. Fix: the writer now
emits canonical `0x`-prefixed addresses. Lesson for pipelines like this: a
checkpoint file that gets regenerated from a database must never be the only
copy of an edit that the import path can silently drop.

Corpus after the symbol pass: 342/1233 functions named (27.7%).

## State

- `build/firmware.syx` ready: 4 keepers + ctlscope pair (emit tap + un-gated
  bottom-row readout). Not flashed yet.
- Device still runs the *old* (superseded) pad-id-scope diagnostic.
- Next session: flash ctlscope → read pad/key/knob ids off the grid → pick the
  page toggle → design the C mod pipeline + page system.
