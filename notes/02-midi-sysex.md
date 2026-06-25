# Launchkey Mini MK3 — MIDI / SysEx

## CoreMIDI ports
- `Launchkey Mini MK3 MIDI Port` — music/keyboard MIDI
- `Launchkey Mini MK3 DAW Port`  — InControl/DAW surface (LEDs, pads, controls)

## Universal Device Inquiry (F0 7E 7F 06 01 F7)
Reply (identical on both ports):
```
F0 7E 00 06 02 00 20 29 02 01 00 00 00 04 02 05 F7
```
Decoded:
- `00 20 29`   manufacturer = Novation
- `02 01`      family  (LSB MSB) = 0x0102  (matches USB PID 0x0102)
- `00 00`      model/member
- `00 04 02 05` firmware version bytes  → current = application mode

Device is in **application mode** (a bootloader-mode reply would differ).

## TODO probes
- Find the SysEx command that triggers **bootloader/DFU entry**.
- Map the InControl/DAW SysEx command set (LED RGB, pad addressing, modes).
  Reference: Novation "Launchkey Mini MK3 Programmer's Reference Guide" (public PDF).
- Determine whether firmware update payload is encrypted/signed.
