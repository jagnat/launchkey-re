# `re/` — the renamed firmware corpus (checkpoint + fast query layer)

This directory is both the **RE checkpoint** (progressively replacing Ghidra's
`FUN_*`/`DAT_*` with real names) and a **pre-computed index** so routine
investigation costs a `grep`, not a 30-second Ghidra launch.

## Source of truth & data flow
```
raw .bin ──import──►  Ghidra project (tools/ghidra_proj/LKMini)   ← THE database
                          │  names live here; rename in GUI or via symbols.tsv
   ImportSymbols.java ◄───┤  replays symbols.tsv onto the project
   ExportCorpus.java  ────┘  regenerates everything below (one launch)
                          ▼
   symbols.tsv   the CHECKPOINT — addr→name map, address-sorted, hand-editable.
                 Reproducible: bin + symbols.tsv + ImportSymbols == annotated project.
   firmware.c    full decompilation, one block per function (derived; do not edit).
   functions.tsv addr name size ncallers ncallees cline nclines signature
                 (cline/nclines = where the function lives in firmware.c → cheap slicing)
   xrefs.tsv     from_addr from_name to_addr to_name kind(call|data) — the call graph + data refs
   strings.tsv   addr string
   data.tsv      addr name type len   (labeled tables/vars)
   coverage.txt  named/total metric
```
The Ghidra `.rep` blob is a **build product** (gitignored) — rebuildable from
`bin + symbols.tsv`. The text artifacts above are what we version; their diffs are
the record of what we understood each session.

## Investigate WITHOUT launching Ghidra (do this first)
```
scripts/q.py fn <name|0xADDR>     signature + callers + callees + that function's C
scripts/q.py callers <name|addr>  who calls it
scripts/q.py callees <name|addr>  what it calls
scripts/q.py xref <0xADDR>        every reference to an addr (great for data tables)
scripts/q.py grep <regex>         search function names + signatures
scripts/q.py str <regex>          search strings
scripts/q.py addr <0xADDR>        which function contains an address
```
Only launch Ghidra to **regenerate the corpus after renames**, or when the static
corpus genuinely lacks the answer (new analysis, type recovery).

## Make a checkpoint (after learning some names)
1. Add confident lines to `symbols.tsv` (or rename in the Ghidra GUI).
2. Regenerate + replay in one launch:
   ```
   GH=/opt/homebrew/Cellar/ghidra/12.1.2/libexec
   "$GH/support/analyzeHeadless" tools/ghidra_proj LKMini \
     -process 'launchkey-mini-mk3_v1.2-build461.syx.bin' -noanalysis \
     -scriptPath tools/ghidra_scripts \
     -preScript ImportSymbols.java -postScript ExportCorpus.java
   ```
3. `git add re/ && git commit` — the diff shows exactly which functions you named.

## Strategy: topological, anchor-and-spread (see MAP.md for the live state)
Name **bottom-up** where it's mechanical (cascades upward as callers become
readable) and **anchor-and-spread** from known I/O where it's logic:
- **L0 ground truth:** vector-table handlers, SVD register names (TODO: SVD-Loader
  pass with `tools/svd/STM32F401.svd`), HAL functions (TODO: BinDiff vs compiled HAL).
- **L1 drivers:** TIM1 LED/key ISR (notes 9–10), USB, GPIO.
- **L2 subsystems:** palette/LED descriptors (11/12/16), velocity (18), `g_settings`.
- **L3 application/musical:** arp/chord/scale — reached from the USB-MIDI RX anchor
  and by climbing out of `g_settings`.

Progress is the `coverage.txt` number plus the per-subsystem state in `MAP.md`.
