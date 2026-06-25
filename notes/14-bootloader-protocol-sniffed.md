# 14 — Bootloader transfer protocol, captured from a real update

Earlier (note 13) we couldn't enter the bootloader: this unit's **old firmware
(build 425 / v1.1.2)** ignored the `00 71` reboot SysEx, and no `Launchkey Mini MK3 BL`
MIDI port ever appeared. So instead of guessing, we **ran a genuine Novation Components
firmware update (v1.1.2 → v1.2) and captured the MIDI** the device sent back
(`scripts/sniff_update.py` → `build/update_capture.log`). That cracked the protocol and,
as a bonus, **updated the unit to v1.2 (build 461)** — the exact base our patch targets.

## Big surprise: no separate bootloader port on this firmware
The **entire update happened on the normal `Launchkey Mini MK3 MIDI Port`.** The device
did *not* re-enumerate into a `…BL` port when it entered the bootloader — USB descriptors
are shared between app and bootloader, so the port name is unchanged. The only USB
re-enumeration was the final **bootloader → updated-app** reboot at the very end. (The
`Launchkey Mini MK3 BL` name in the Components bundle must be for newer units/firmware.)
This is why all of note 13's "watch for a BL port" attempts were doomed.

## The device→host messages (what we captured)
All framed `F0 00 20 29 <cmd> … F7` (Novation mfr `00 20 29`):

| cmd | name | example | meaning |
|---|---|---|---|
| `00 42` | SERIAL | `00 42 02 "A4F9KBX2127660"` | unit serial number (ASCII) |
| `00 70` | VERSION | `00 70 00 00 04 01 07 00 00 04 02 05 20 01` | bootloader v`4.1.7` + **app build `4 2 5`=425** |
| `00 72` | ACK | `00 72 <lo> <hi> 00` (×2753) | per-packet ack; count = `hi*128+lo` |
| `00 73` | END-ACK | `00 73 7F 7F 7F` | transfer complete |

- **Build number is encoded as its 3 decimal digits**, one per byte: `04 02 05` = "425",
  and after the update `04 06 01` = "461" = v1.2. (Matches the device-inquiry tail and
  confirms the flash succeeded.)
- The **`00 72` ACK is the flow-control heartbeat**: after each firmware packet the host
  sends, the bootloader replies with the running count of packets received. The counter
  went `1 … 2753` (last = `41 15` → 21·128+65 = 2753), i.e. ~2752 DATA + END. The host
  must **wait for each ACK before sending the next packet.**

## Timeline of a real update (from the capture)
```
33.42s  00 42  serial report
33.50s  00 70  version report (old build 425)   <-- bootloader announces itself
33.5–47.5s   (~14 s gap)                          <-- SCENE LAUNCH confirmation window
47.52s  00 72 01 00 00   first packet ACK         <-- transfer begins
 …      00 72 <n>        2753 ACKs total
58.59s  00 73 7F 7F 7F   END ack                   <-- transfer complete
60.97s  ports VANISH                               <-- reboot bootloader -> app
63.28s  ports RETURN
63.38s  00 70 … 04 06 01  version report (new build 461 = v1.2)
```

## What we still don't have: the host→device side
We only sniffed device→host. Unknown host commands: the **reboot/enter-bootloader
trigger**, the **queries** that elicit `00 42`/`00 70`, and the exact on-wire **packet
framing** (we have the `.syx` records, which is almost certainly what's sent). To get the
host side, capture with a CoreMIDI spy (Snoize **MIDI Monitor**, "Spy on output").

## Why this unblocks us
1. The unit is now **v1.2 (build 461)** — newer firmware may honor the `00 71` reboot the
   old build ignored, so bootloader entry is worth re-attempting.
2. We now know the **complete transfer handshake** (ACK-per-packet, END-ack), so once in
   the bootloader we can drive our patched `.syx` and verify each `00 72` ACK.
3. Recovery is proven: Components can always reflash, and the bootloader shares the port.

## Entry re-test on v1.2 — `00 71` STILL ignored
`scripts/entry_test.py` (sent both `00 71 02 0B …` and `00 71 01 02 …` to the MIDI Port,
Scene Launch ready): **no response on v1.2 either.** So the host→device bootloader-entry
trigger is NOT a bare `00 71` reboot — Components uses some other sequence we never
captured (we only sniffed device→host). The `00 71`/`rebootToBootloader` in the bundle is
the *UI reboot button*, which this firmware apparently doesn't act on; the *update flow*
(`tryFirmwareUpdate`→`#Ei` sends `#Si[0]`, then waits for status "bootloader") must差.

## Real options to get the host→device trigger
1. **MIDI Monitor spy (definitive).** Install Snoize **MIDI Monitor**, enable "Spy on
   output", and have Components send firmware again. Since the unit is already v1.2,
   trigger a re-send via Components (downgrade to v1.1.2 first if it won't re-flash the
   same version — we still have `firmware/launchkey-mini-mk3_v1.1.2-build425.syx`). The
   spy reveals the exact reboot command + packet framing; combine with the known ACK loop
   to write a complete flasher.
2. **SWD hardware route (note 08).** Bypass MIDI entirely; most reliable now.
3. **More static RE** of the Components bundle's `tryFirmwareUpdate`/`chunkFirmware` to
   reconstruct the host→device sequence without hardware.
