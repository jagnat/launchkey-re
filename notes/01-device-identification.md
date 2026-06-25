# Launchkey Mini MK3 — Device Identification

## USB identity (captured via `ioreg` 2026-06-23)
| Field | Value |
|---|---|
| Product | Launchkey Mini MK3 |
| Vendor | Focusrite A.E (Novation) |
| VID | `0x1235` (4661) |
| PID | `0x0102` (258) |
| bcdDevice | `0x0200` → likely fw/device rev **2.00** |
| bcdUSB | 2.00 |
| Serial | A4F9KBX2127660 |
| bMaxPacketSize0 | 64 |
| bNumConfigurations | 1 |

## Interfaces (firmware-exposed)
- **Audio Control** (class 1 / subclass 1) — `Launchkey Mini MK3 MIDI`
- **MIDI Streaming** (class 1 / subclass 3, 2 endpoints) — `Launchkey Mini MK3 MIDI Int`
- **CDC-ACM** control (class 2 / subclass 2 / protocol 1) + **CDC Data** (class 10, 2 endpoints)
  → exposes a *virtual serial port*. Purpose TBD (DAW handshake? diagnostics?).
- **Class 0x11 (17)**, 0 endpoints — non-standard, investigate.

Two MIDI ports are presented:
- `Launchkey Mini MK3 MIDI`     → normal music/keyboard MIDI
- `Launchkey Mini MK3 MIDI Int` → "InControl"/DAW surface port (LEDs, pads, controls)

## Open questions
- Exact MCU? (Not yet known — do NOT assume. Determine via SWD dump or chip markings.)
- Is the SysEx firmware-update payload encrypted/signed?
- What is the class-0x11 interface for?

## Useful reference
- Novation open-sourced **Launchpad Pro MK1** firmware (github: dvhdr/launchpad-pro,
  and the official `Launchpad-Pro` repo). Same company → same SysEx bootloader/DFU
  conventions are a strong reference even though the Launchkey isn't open.
