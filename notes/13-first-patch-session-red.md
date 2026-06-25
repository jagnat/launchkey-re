# 13 — First real patch: session idle blue → red (route A)

Goal of this milestone: prove we can take the stock image, change **one palette
entry**, re-encode to `.syx`, and have a flashable file — the reversible "route A"
confirmation that palette index 12 really is the standalone Session-mode idle colour.
No hardware was attached; the deliverable is the built+verified binary, to flash later.

## The patch itself (trivial part)
Palette lives at file offset `0x14250` (flash `0x0801C250`), 128 entries × 4 bytes
`R,G,B,pad`. Entry 12 = offset `0x14280`:

```
0x14280:  2F AF FF 00   ->   7F 00 00 00
          (47,175,255)       (127,0,0)  muted red, half-brightness
          session cyan
```

Edit the byte in the decoded `.bin`, then re-encode. Because re-encode handles the
7-bit packing and the transfer CRC, we never touch the SysEx encoding by hand.

## The two gotchas (the actual lesson)
A "no-op round-trip" — decode the stock `.syx`, immediately re-encode it, and compare
to the original — is supposed to be a zero-risk warm-up (note 08). It paid off twice:

### Gotcha 1 — the installed `xkey` encoder is broken
The PyPI `xkey` in `.venv` produces a `.syx` that **its own decoder can't read**
("Unsupported SysEx message …"). Cause: its `encode` loop never pads the final partial
chunk. The image's last chunk is 24 bytes; it must be padded to 32 (with `0xFF`, the
erased-flash value) before encoding, so it encodes to the canonical 37-byte DATA
record. The installed version skips the pad → a 28-byte final record → every following
byte is misframed → unparseable, and the device would reject it (or under-write the
last 8 bytes of flash).

The **`tools/xkey/` source clone is a newer, fixed version** that pads correctly
(`if len(buffer) < FIELD_CHUNK_SIZE: buffer.extend([0xFF]*…)`). Fix: encode using the
source, not the installed CLI:

```sh
PYTHONPATH=tools/xkey python -c "import sys; \
  sys.argv=['xkey','encode','build/session-red.bin','--model','launchkey-mk3','--build','461']; \
  from xkey.cli import entrypoint; entrypoint()"
```

Lesson: a decode that succeeds does **not** prove the matching encode is correct.
Always round-trip in *both* directions and diff the bytes.

### Gotcha 2 — xkey targets the full-size Launchkey, not the Mini
xkey's START message device id is `MANUFACTURER("Novation")=0x02` + `MODEL("launchkey-mk3")=0x0F`
= **`02 0F`**, which is the *full-size* Launchkey MK3. The **Mini MK3 is `01 02`**
(note 04). The bootloader's device-id interlock would refuse a `02 0F` file. So after
encoding we patch START bytes 6–7 back to `01 02`:

```python
b[6:8] = bytes([0x01, 0x02])   # F0 00 20 29 00 71 <here> ...
```

The METADATA transfer-CRC is computed over the firmware payload only, **not** the START
device id — proven because the CRC bytes were identical whether the id was `02 0F` or
`01 02`. So post-patching those two bytes invalidates nothing.

## Verification (why we trust the file without hardware)
1. **No-op identity:** decode stock → re-encode (fixed) → patch device id ⇒ output is
   **byte-for-byte identical** to Novation's shipped `.syx`. The whole toolchain is a
   true inverse pair.
2. **Binary round-trip of the patch:** decode our patched `.syx` back to a `.bin`; it
   differs from stock at **exactly** `0x14280-0x14282` (`→ 7f0000`) and nowhere else.
3. **SysEx diff vs shipped firmware** is minimal and fully explained:
   - `0x24–0x2B` — METADATA CRC field (image CRC `0x1eb7f365` → `0x737dd2d3`, auto-recomputed).
   - `0x1bb77–0x1bb7a` — the single DATA record carrying file offset `0x14280`.
   - START device id now matches shipped (`01 02`), so it is **not** in the diff.

## Artifacts
| File | What |
|---|---|
| `build/session-red.bin` | patched raw image (88,088 B, CRC32 `0x737dd2d3`) |
| `build/launchkey-mini-mk3_v1.2_session-red.syx` | **flashable** patched SysEx (121,177 B) |
| `firmware/launchkey-mini-mk3_v1.2-build461.syx` | stock recovery image (unchanged) |

## Flashing — BLOCKED on bootloader entry (2026-06-25 hardware session)
We tried to flash and hit a wall: **we cannot get this unit into the Novation MIDI
bootloader.** Findings (device was connected the whole time):

- **Device is healthy & responsive.** Universal Device Inquiry replies
  `7E 00 06 02 00 20 29 02 01 00 00 00 04 02 05`; in DAW mode it echoes `9F 0C 7F` and
  we captured live button presses (`BF 73 7F` = Scene Launch, `B0 68` = another). Comms
  on both **MIDI Port** and **DAW Port** confirmed.
- **Components' reboot-to-bootloader command:** `F0 00 20 29 00 71 <pid0> <pid1> 00 00 F7`
  to `mainOutput`, where LK Mini MK3 `productId = [2,11] = 02 0B` (from the bundle —
  NOT the firmware START id `01 02`). The bootloader would re-enumerate as a MIDI port
  named **`Launchkey Mini MK3 BL`**.
- **But this unit ignores `00 71` entirely.** Tried both ids (`02 0B` and `01 02`), both
  ports, with DAW/InControl mode enabled (`9F 0C 7F`) and with the Scene Launch
  confirmation pressed. No port change, no reaction. Likely because this unit runs the
  **older firmware (build 425 / v1.1.2)**; Components' `firmwareIsNotCompatible` gate is
  `firmwareVersion < 271`, so old units may use a different/older update entry.
- **Manual `Octave+ & Octave−` on power-up did NOT surface a MIDI `BL` port** either
  (that combo may instead enter STM32 USB-DFU, a different non-MIDI path — unverified).
- **Transfer protocol (for when we do get in):** request/response handshake — host sends
  a packet, waits for the bootloader to request the next (Components state machine
  `WAITING_FOR_PACKET_REQUEST`; END command byte = `0x73`). NOT a blind stream.

**Recovery/cleanliness:** nothing was written; only DAW-enable/disable + device-inquiry
were sent. Device left in standalone mode.

### Next-step options to actually flash (pick one)
1. **Sniff a real Components update (recommended, non-invasive).** Run Novation
   Components' official updater (it will offer v1.1.2 → v1.2) while capturing MIDI with
   a spy tool (e.g. Snoize **MIDI Monitor**, which sees host→device CoreMIDI traffic).
   This reveals the exact reboot + handshake for *this* unit, and updates it to v1.2
   (matching our patch base). Then replay the captured sequence with our patched image.
2. **SWD hardware route (note 08).** ST-Link/J-Link/Pi-Pico on the SWD pads → write the
   app region directly + dump current flash as backup. Most robust; needs opening the case.
3. **More static RE** of how the v1.1.2 app enters its bootloader before touching hw again.

## What to look for once flashing works
- **Expected result:** standalone Session-mode idle pads come up **red** instead of cyan
  ⇒ palette index 12 confirmed, de-risking route B.
- **If boot-loop/reject:** suspect an app self-CRC (note 08). Recoverable — reflash stock;
  SysEx never writes the bootloader region.
</content>
</invoke>
