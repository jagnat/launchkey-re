# 17 — Roadmap: building a working model & extending the firmware efficiently

The palette hunt worked but was expensive because it leaned on the slow loop
**flash → human looks → report**. To go after musical features (arp, scale/sweep,
chord) without burning budget, we lean on two superpowers we now have, plus a few
force-multiplier tools, so most work happens **offline and in batches**.

## Two superpowers we already hold
1. **It's HAL/CubeMX firmware** (note 06) — huge swaths are recognizable library code we
   can auto-label instead of reading by hand.
2. **We can flash + observe freely** (note 16) — controlled experiments are cheap, and
   **MIDI output is a precise, programmatic observation channel** (capture the notes the
   device emits, like we sniffed the bootloader) — far better than eyeballing LEDs.

## Force multipliers (do these once, save weeks)
### A. Recover symbols en masse — offline, no hardware
- **HAL diffing:** compile the *same* STM32 HAL/CMSIS version with `arm-none-eabi-gcc`,
  then **BinDiff or Diaphora** to match functions → auto-names hundreds of HAL routines
  (GPIO/TIM/USB/DMA/I2C/SysTick). Collapses the manual naming slog.
- **SVD-Loader (Ghidra) + STM32F401 SVD:** auto-annotates every peripheral register
  access, so the decompiler shows `TIM1->CCR1` not `*(0x40010034)`. Instantly reveals
  which code drives which peripheral.
- FLIRT / Function-ID for libc/compiler helpers.
→ Output: a Ghidra project where most functions are named and register I/O is labeled.
  That *is* the first "working model."

### B. Stand up a runnable model — emulation
- **Renode** supports STM32F4. Load our `.bin`, model the peripherals we care about
  (USB-MIDI, the TIM/GPIO LED+key matrix), and actually **run** the firmware. Then:
  breakpoints, execution trace ("what runs when I press pad X"), memory watchpoints on
  the LED descriptors / note buffers. Replaces most guess-and-flash with introspection.
- Lighter option: **Unicorn/QEMU** harness to run *one* function (e.g. the arp engine)
  with synthetic inputs and read outputs — great for isolating musical logic.

### C. Anchor on I/O contracts we already understand
- **MIDI/SysEx is documented** (Components bundle + Novation programmer's reference).
  Every MIDI message is a labeled entry/exit point. Find the **USB-MIDI RX handler** →
  follow to the **note/CC dispatch** → you're standing inside the musical engine.
- We already mapped the **LED scan**; the **key-scan** is the other half of the TIM1 ISR
  matrix → find where key events get queued → that queue feeds arp/note logic.

## Targeting the musical features
Arp / scale / chord are pure logic over **note events + timing**. The "knobs" are tables:
- **Scale/chord tables:** small arrays of semitone offsets (e.g. major = `0,2,4,5,7,9,11`;
  chord intervals like `0,4,7`). Easy to spot by pattern-scanning the binary.
- **Arp:** a tempo source (a timer/SysTick tick), a **held-note buffer**, an **arp
  pattern/step table**, and **rate divisors** (1/4,1/8,1/16,triplets). Find these and you
  control arp behavior.
- Method: locate tables statically → change one → **capture MIDI out** to verify exactly
  what notes change (no eyeballing). The dim-LED/arp result is then deterministic.

## Difficulty, honestly
- **Tweak existing tables/constants** (arp patterns, scales, velocity curves, colors):
  *easy* — same workflow as the palette, now with MIDI-capture verification.
- **Add new behavior** (a new arp mode/feature): *medium* — need a hook point + spare
  flash/RAM to inject code (check app-region slack & unused handlers). Feasible.
- **Full C rebuild** (the stretch goal): *large* — but the model + recovered symbols feed
  it directly; it's a long arc, not a prerequisite to start hacking features.

## Recommended next session (highest leverage first)
1. **Symbol recovery pass:** SVD-Loader + HAL BinDiff → annotated decompile (offline).
2. **Find the MIDI RX → note-dispatch path** (the gateway to all musical features).
3. Pick one easy win to prove the loop: locate the **scale/chord interval tables** and
   change one, verified by **capturing MIDI out** — the audio-domain analog of the palette
   win, with zero human eyeballing.
4. Optional but powerful: bring up **Renode** so future questions are answered by tracing,
   not flashing.

## Efficiency rules for us
- Prefer **offline static + emulation** over the flash/observe loop.
- When we must observe, use **MIDI capture** (exact) over visual, and **batch hypotheses**
  into one experiment (like the 3-flash band search vs 19 one-offs).
- Keep building **reusable scripts** (`flash.py`, palette tools, a MIDI-capture helper).
</content>
