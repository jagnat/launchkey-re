# 15 — Full firmware-update protocol, reconstructed from the Components JS

Note 14 captured the **device→host** side; here we reverse-engineer the **host→device**
side statically from `tools/components-main.js` so we can write our own flasher. Together
these give the complete two-way protocol.

## The buffers (`#Si`) = the `.syx` messages, in order
`updateFirmware` chunks the `.syx` (in a worker) into a list `#Si` of whole SysEx
messages: `[START(00 71), METADATA(00 7C), DATA(00 72) × ~2752, END(00 73)]`. An index
`#Mi` walks the list; `#xi` tracks the highest packet count the device has acked.

## Host→device sequence (decompiled control flow)
```
updateFirmware(file):
  #Si = chunk(file);  #Mi = 0;  #xi = -1
  tryFirmwareUpdate(#Si[0])

tryFirmwareUpdate(start):                 # enter the bootloader
  #Ei(start)  ->  mainOutput.send(START)  # send the .syx START to the MAIN (app) port
  wait until status == "bootloader"       # app reboots into bootloader (same MIDI port
                                          #   on this unit — NO separate 'BL' port)
  startFirmwareTransfer()

startFirmwareTransfer():                  # ACK-driven streaming
  listen for midimessage -> #Oi
  #Ii()                                   # kick off

#Ii():                                    # send the next packet
  pkt = #Si[#Mi++];  output.send(pkt)
  if nextPacket is METADATA(0x7C) and sendFirmwareInfoHeader:
        #xi = -1; #Ii()                   # send START then METADATA back-to-back, no wait
  elif pkt[5] != 0x73 (END) and #Mi != len:
        arm timeout; wait for ack         # wait for the device's 00 72 ack
  else: transfer complete
```

## Device→host replies (`#Oi`, from the cmd byte `e[5]`)
- **`00 72` DATA-ACK** → `#Fi(e[6:9])`: `count = e6 + (e7<<7) + (e8<<14)`. If
  `count > #xi` (or `==0`), set `#xi = count` and call `#Ii()` → **send the next packet**.
  (A 15-byte variant routes to `#Ri` with a different bit layout — checksum mode, unused
  here.) Our capture: `00 72 <lo> <hi> 00`, count ran 1 → 2753.
- **`00 73` STATUS / END** → `#zi(e)`: 10-byte msg, status `e[6]` ∈
  `{initiateUpgrade, waitingForUserConfirmation, waitingForUserConfirmationTimeout, …}`.
  **`waitingForUserConfirmation` is the “press Scene Launch” prompt.** The capture's final
  `00 73 7F 7F 7F` is the transfer-complete marker.

## So the complete wire conversation (host = us, dev = bootloader)
```
host -> dev : START   (00 71 01 02 00 00 00 04 06 01)      # trigger reboot to bootloader
   (user presses SCENE LAUNCH to confirm; dev may emit 00 73 waitingForUserConfirmation)
host -> dev : START   (again, first transfer packet)
host -> dev : METADATA (00 7C … size+crc)                  # sent immediately after START
dev  -> host: 00 72 01 00 00                               # ack count 1  (metadata rx'd)
host -> dev : DATA #1  (00 72 <37 bytes>)
dev  -> host: 00 72 02 00 00                               # ack 2
   … repeat: send DATA #k, wait for ack k+1 …  (2752 DATA, acks reach 2753)
host -> dev : END     (00 73 <last chunk>)
dev  -> host: 00 73 7F 7F 7F                               # complete
   (device reboots into the new app; ports re-enumerate)
```

## Build-number & version encoding (handy)
`00 70` version report carries the build as **three decimal-digit bytes**: `04 02 05`=425
(v1.1.2), `04 06 01`=461 (v1.2). Bootloader version was `04 01 07` = 4.1.7.

## The one thing static RE can't settle
Per the JS the entry trigger is simply **sending the `.syx` START to the main MIDI port**,
plus the **Scene Launch** confirmation. Whether START *alone* flips this v1.2 unit into
the bootloader, or the physical Scene Launch press is what actually arms it, can only be
confirmed on hardware. Our flasher (`scripts/flash.py`) implements the sequence above and
**aborts before sending any DATA if it doesn't see the first `00 72` ack** — so a failed
entry writes nothing (START+METADATA carry no firmware bytes).

## Flasher
`scripts/flash.py <patched.syx>` — dry-run by default (parses + prints the plan); add
`--go` to actually stream. Implements the ACK-driven loop, prompts for Scene Launch,
times out safely if the bootloader never acks. See note 13 for the verified image and
note 08 for recovery (reflash stock via Components; bootloader is never written by SysEx).
</content>
