# Launchkey Mini MK3 firmware — project guide

**Primary goal:** ship **targeted firmware mods** (LED colours, arp, scales/chords,
velocity) to the Novation **Launchkey Mini MK3** (STM32F401, Cortex-M4) by reverse-
engineering, then flashing a patched image. **Don't break things** — favour reversible,
low-risk changes; validate with no-flash methods first; never flash without an explicit
go-ahead.
**Ancillary goal:** a full semantic map of the firmware — worth growing coverage when
convenient, but secondary; never let map-building risk the working device or a shippable mod.

This file is **stable**: it does not track current status. Live status lives in
`re/MAP.md` (see below) and is updated as work proceeds.

## Start here — every new context

1. **Read `re/MAP.md` first** (it is small — status, dead-ends, index, quick reference).
   Then open ONLY the `re/map/*.md` topic sheet(s) the task needs (the index in MAP.md says
   what each contains). This is the init — start nowhere else, load nothing else up front.
2. **Do NOT read `notes/`** unless the user names a specific file. `notes/` is a human
   teaching log: large, narrative, written for the user — not for Claude context. All
   facts Claude needs must live in `re/MAP.md` + the `re/` corpus, not in a note.
3. **Don't bulk-load big files** into context: `re/firmware.c` (~33k lines), any
   `*.thumb.asm`, full hexdumps. Slice them via `scripts/q.py`.

## Investigate cheaply — don't launch Ghidra for lookups

- Query the pre-exported `re/` corpus with **`scripts/q.py`**: `fn`, `callers`,
  `callees`, `xref <0xADDR>`, `grep <re>`, `str`, `addr`, `reg <REG>`. Tiny token cost.
- Or `grep re/*.tsv` directly.
- **Ghidra headless only** to regenerate the corpus after renaming symbols, or for
  genuinely new analysis the static corpus can't answer. Regen in one launch:
  `analyzeHeadless tools/ghidra_proj LKMini -process
  'launchkey-mini-mk3_v1.2-build461.syx.bin' -noanalysis -scriptPath
  tools/ghidra_scripts -preScript ImportSymbols.java -postScript ExportCorpus.java`.

## Hardware in the loop

- The device is a **MIDI black box** — drive + observe it live with
  `scripts/midi_capture.py` (no flashing, zero risk). Prefer **measured MIDI** to the
  slow flash→eyeball loop when validating a hypothesis. Measured facts: `re/map/validation.md`.
- **Building:** `mods/build.py` is the canonical accumulating build — its `MODS` list is the
  **single source of truth for what an image contains**. What is actually *flashed on the
  device* is recorded in `re/MAP.md` Current status; keep the two in sync at every flash.
- **Flashing:** `.venv/bin/python scripts/flash.py build/firmware.syx --go` **must run in the
  background**; it is reversible (a bad image → bootloader keeps the prior firmware).
  **Never flash without an explicit go-ahead from the user.**
- Run scripts with **`.venv/bin/python`** (mido lives there, not in system python).

## Stable toolchain gotchas

- **Encode `.syx` via the `tools/xkey/` source clone, not the installed PyPI `xkey`**
  (its encoder doesn't pad the final chunk → emits a file its own decoder rejects).
- `xkey` emits device id `02 0F` (full Launchkey MK3); the **Mini MK3 needs `01 02`** —
  patch `.syx` bytes 6–7 after encoding (transfer CRC doesn't cover them).
- App load base `0x08008000`. Use **Ghidra**, not rizin/objdump, on code/data-ambiguous
  regions (raw flat-map mis-parses Thumb literal pools).
- **Ghidra headless** lives at `/opt/homebrew/Cellar/ghidra/12.1.2/libexec/support/
  analyzeHeadless` and needs **Java 21** (`JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/
  openjdk.jdk/Contents/Home`; system default `java` is 24 → Ghidra 12.1.2 rejects it). If a
  prior run cached scripts under Java 24 you'll hit `UnsupportedClassVersionError (class file
  68 vs 65)` — fix by clearing `~/Library/ghidra/ghidra_12.1.2_PUBLIC/osgi/compiled-bundles/*`
  so it recompiles the `.java` under 21.

## Keeping context small (the point of this layout)

- One source of truth for Claude: **`re/MAP.md` (init) + `re/map/*.md` (reference sheets) +
  the `re/` corpus + `scripts/`**.
- If a fact matters going forward, put it in the right **`re/map/*.md` sheet**, not in a
  teaching note. New symbol names → `re/symbols.tsv` + corpus regen.
- After each milestone: **rewrite `re/MAP.md`'s "Current status" IN PLACE** — current truth
  only, ≤40 lines, never append checkpoints or corrections (history = git log + notes).
  Proven dead ends get one line in MAP.md's dead-ends list. Then write/update a human
  teaching note in `notes/NN-*.md` (explain the *why*, not just the result), and offer
  the user a commit — the old-state record is git history, not prose in MAP.md.
