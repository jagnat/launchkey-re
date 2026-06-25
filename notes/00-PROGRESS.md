# Launchkey Mini MK3 firmware RE — progress & learning log

This is the index. Each numbered note is a self-contained lesson covering both
**what** we found and **how** we reasoned to it, so you can follow the process.

## Where we are
- [x] **01** Identify the device (USB descriptors, MIDI identity)
- [x] **02** Talk to it over MIDI/SysEx
- [x] **03** Obtain the firmware (pulled from Novation's own servers)
- [x] **04** Understand the `.syx` firmware-update format + decode to raw binary
- [x] **05** Locate the binary in memory (load address, flash map, vector table)
- [x] **06** Map peripherals from the firmware (+ discovered it's HAL/CubeMX code)
- [x] **07** Ghidra set up; found hw-init; learned HAL-handle tracing
- [x] **08** Flashing & safety reference (recoverable via bootloader; round-trip plan)
- [x] **09** Found the LED+key engine: TIM1-ISR multiplexed matrix scan (FUN_080095a8)
- [x] **10** LED engine internals: 8×16 BCM matrix, R/G/B bit-planes, drivers mapped
- [x] **11** Found 128-colour palette @0x0801C250; session idle ≈ index 12 (47,175,255)
- [x] **12** LED descriptor layer mapped; route-B snag identified (wide-store writer)
- [x] **13** First patch built+verified: session idle blue→red (route A), ready to flash
- [x] **14** Bootloader transfer protocol sniffed from a real update; unit now on v1.2
- [x] **15** Host→device update protocol reconstructed from JS; flasher `scripts/flash.py` built
- [x] **16** FLASHED custom fw successfully! Palette is B,G,R; session idle ≠ idx 12
- [x] **GOAL ACHIEVED** Session idle recolored blue→red (palette **index 42**), flashed & confirmed on hw
- [x] **17** Roadmap: efficient firmware modeling & extending (symbol recovery, Renode, MIDI-capture)
- [x] **18** First offline musical-table find: **velocity curves** @0x0801a158 + full code path
- [x] **19** USB-MIDI RX path mapped: router/publish/note-state tables (engine gateway)
- [ ] later: extend musical features (arp/scale/chord) per note 17; route B; custom C firmware
- [ ] later: USB-MIDI RX path + InControl/DAW SysEx protocol
- [ ] later: custom firmware (CubeMX project, linker @0x08008000, flashing)

## ▶ RESUME HERE (as of 2026-06-24)
**Route A patch is BUILT and VERIFIED — waiting on hardware to flash-test.** User went
with route A (reversible palette[12]→red confirmation). See **note 13** for the full
write-up. No hardware was attached; we produced + verified the flashable file for later.

**Flashable artifact:** `build/launchkey-mini-mk3_v1.2_session-red.syx`
(palette[12] `2F AF FF 00`→`7F 00 00 00`; image CRC32 `0x737dd2d3`).

**Two toolchain gotchas found & handled (note 13):**
1. Installed PyPI `xkey` encoder is **broken** (doesn't pad the final chunk → file even
   its own decoder rejects). Use the **`tools/xkey/` source** instead:
   `PYTHONPATH=tools/xkey python -c "...entrypoint()" encode … --model launchkey-mk3 --build 461`.
2. xkey emits device id `02 0F` (full-size MK3); **Mini needs `01 02`** — patch START
   bytes 6–7 after encoding. (Transfer CRC doesn't cover those bytes; verified.)

**Verified without hardware:** no-op round-trip is **byte-identical** to shipped
firmware; patched image differs from stock at exactly `0x14280-82` (`→7f0000`) and the
syx differs from shipped only in the METADATA CRC + the one DATA record + matching id.

**2026-06-25 — bootloader protocol CRACKED + unit updated to v1.2 (note 14).** Sniffed a
real Components update (`scripts/sniff_update.py` → `build/update_capture.log`). Key facts:
- Old build 425 ignored `00 71`; we ran the official update → **unit is now v1.2 (build
  461)**, matching our patch base. (Build # = 3 decimal-digit bytes: `04 02 05`=425 →
  `04 06 01`=461.)
- **Bootloader runs on the SAME `MIDI Port`** — no separate `…BL` port on this firmware.
- Device→host handshake: `00 42`=serial, `00 70`=version(boot `4.1.7`+app build), `00 72
  <lo> <hi> 00`=per-packet ACK (count=hi*128+lo, ran 1→2753), `00 73 7F 7F 7F`=END ack.
- Flow control: host sends packet → wait for `00 72` ACK → next; ~14s Scene-Launch
  confirm gap before transfer. Still missing: the host→device reboot trigger + framing.

**Entry re-test on v1.2: `00 71` still ignored** (`scripts/entry_test.py`). So bootloader
entry is NOT a bare `00 71` reboot. Did **static RE** of the Components JS instead
(note 15): full host→device protocol reconstructed — trigger = send the `.syx` **START**
to the MIDI port + **Scene Launch** confirm; then ACK-driven stream (START, METADATA, then
DATA waiting for `00 72 <count>` acks, END → `00 73` complete). Build flasher
`scripts/flash.py` (dry-run default, `--go` to stream; aborts before any DATA if no ack).
Dry-run parses our patch as START/METADATA/2752×DATA/END ✓.

**2026-06-25 — FLASHING WORKS (note 16).** `python scripts/flash.py <file.syx> --go`,
run in **background** (a short foreground Bash timeout will kill it mid-transfer → safe
revert), press **Scene Launch** when prompted (~3s in), ~40s. Entry trigger = the flasher
sends START; Scene Launch confirms. Two findings: (1) **palette is B,G,R not R,G,B** —
red = file `00 00 7F` (idx5=`00 00 FF`=red, idx21=`00 FF 00`=green); (2) **session idle is
NOT idx 12** (idx12 = orange in BGR). Changing all entries DID move the session pads, so
session uses some palette index whose stock value is cyan.

**NEXT:** finding the session-idle index via **marker flashes** (paint candidate cyan
indices distinct colors, see which the session pads adopt). Tested negative: idx
{36,37,40,41,78,91} (round 1), round 2 = {32,33,48,90,115,116}. Once found, flash final
patch: that index → `00 00 7F` (red). Verified images in `build/`. DO NOT flash without
explicit user go-ahead.

**If continuing route B (surgical):** find the **wide store / template** that writes
the colour index (likely a 32-bit write to descriptor `+0xc`, colour in high byte)
into the session pads' descriptors @ `0x20003868`. Search for the confirmed index
constant once known. See note 12.

**Key addresses for the patch**
| Thing | Value |
|---|---|
| Palette base | `0x0801C250` (file off `0x14250`), 128×4 bytes R,G,B,pad |
| Palette entry 12 | file off `0x14280` = `2F AF FF 00` (≈ session blue/cyan) |
| LED descriptor array | RAM `0x20003868`, 16 B/LED; `+0xf` = colour index |
| Render (reads palette) | `FUN_080141c2` (and `FUN_080141b8`) |
| Physical LED RGB buffer | RAM `0x2000AE40` |
| Stock syx (recovery) | `firmware/launchkey-mini-mk3_v1.2-build461.syx` |

## The big picture (one paragraph)
The Launchkey Mini MK3 is an **STM32F401** (ARM Cortex-M4) device. Its 128 KB
flash is split into a **bootloader** (`0x08000000`, 32 KB) and the **application**
(`0x08008000`, ~88 KB). Novation ships firmware as **plaintext** MIDI SysEx `.syx`
files (no encryption/signing) downloadable without auth from
`components.novationmusic.com/api/v2/firmwares`. We downloaded v1.2 (build 461),
decoded the SysEx wrapper to a raw binary, found its load address from the
Cortex-M vector table, and confirmed it disassembles cleanly. That's the whole
foundation — from here it's normal firmware reverse engineering.

## Key facts cheat-sheet
| Thing | Value |
|---|---|
| MCU | STM32F401 (LQFP64 → F401Rx), Cortex-M4, 128 KB flash, 64 KB SRAM |
| USB VID:PID | `0x1235:0x0102` |
| Bootloader region | `0x08000000`–`0x08007FFF` (32 KB) |
| App load address | **`0x08008000`** |
| App image (v1.2) | 88,088 bytes (`0x15818`) |
| Reset handler | `0x0801D251` |
| SystemInit | `0x0801CF15` |
| App entry (`_start`) | `0x0801D1E5` |
| Firmware format | plaintext SysEx, manufacturer `00 20 29` (Novation) |
| Device id in START | `01 02` (Mini MK3) |
| Your unit's fw | build 425 = v1.1.2 |
| Latest fw | build 461 = v1.2 |

## Tools in this project
- `.venv/` — python venv: `mido`, `python-rtmidi` (MIDI), `xkey` (syx<->bin codec)
- `tools/xkey/` — xkey source (read it to learn the codec)
- `tools/components-main.js` — Novation Components web app bundle (where we found the API)
- `arm-none-eabi-objdump` — Cortex-M disassembly (already installed on this machine)
- `scripts/probe.py` — list MIDI ports + send Universal Device Inquiry
