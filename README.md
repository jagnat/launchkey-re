# Launchkey Mini MK3 firmware mods

Reverse-engineering and binary-patching the stock firmware of the Novation
Launchkey Mini MK3 (STM32F401, Cortex-M4) to add features it doesn't ship with:
a Euclidean arpeggiator, a custom LED palette, and a C-authored UI layer that
takes over the pad grid with its own pages — all without a debugger (no SWD
access), validated over MIDI before anything is flashed.

**No Novation code is distributed here.** The patcher applies mods to the stock
image, which you download from Novation yourself (step 2 below). Built
images are not published.

> Unofficial and unaffiliated with Novation / Focusrite. Flashing modified
> firmware is at your own risk. A bad image is rejected by the bootloader,
> which keeps the prior firmware, but no guarantees.

## What's here

| path | contents |
|---|---|
| `mods/build.py` | the patcher: its `MODS` list defines the image; inline byte patches + appended C/asm payloads with detours |
| `mods/c/`, `mods/asm/` | mod payloads (UI layer, Euclid rhythm engine, glue) |
| `re/MAP.md`, `re/map/*.md` | the firmware map: subsystems, hook seams, verified dead ends |
| `re/*.tsv` | symbol / function / xref corpus exported from Ghidra |
| `scripts/` | corpus query tool (`q.py`), MIDI capture harness, flasher, recon scans |
| `tools/ghidra_scripts/` | headless Ghidra import/export scripts |
| `notes/` | chronological write-ups of the investigation |

## Build

```sh
python3 -m venv .venv && .venv/bin/pip install mido python-rtmidi
git clone https://github.com/darkarnium/xkey tools/xkey   # tested at 3300124
.venv/bin/python scripts/fetch_firmware.py     # stock v1.2 (build 461) -> build/stock.bin, SHA-256 checked
.venv/bin/python mods/build.py                  # -> build/firmware.syx
.venv/bin/python scripts/flash.py build/firmware.syx --go
```

Needs `arm-none-eabi-gcc` for the C payloads. To regenerate the Ghidra corpus
(including `re/firmware.c`, the decompilation, which is not committed), see
`re/README.md`.
