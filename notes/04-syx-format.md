# 04 — The `.syx` firmware-update format

A `.syx` file is just a stream of MIDI **System Exclusive** messages, each framed
`F0 … F7`. Novation's firmware updates use four message types. Every message:
```
F0  00 20 29  <cc>  <payload…>  F7
    |_______|  |__|
    Novation   command (2 bytes)
    mfr id
```

## The four commands (observed in build 461)
| cmd | name | role |
|---|---|---|
| `00 71` | START    | announce device id + protocol/version |
| `00 7C` | METADATA | build number (ASCII) + date/CRC bytes |
| `00 72` | DATA     | one chunk of firmware bytes |
| `00 73` | END      | final chunk; signals completion |

### START — `F0 00 20 29 00 71 01 02 00 00 00 04 06 01 F7`
`01 02` = device identifier for **Launchkey Mini MK3** (matches USB PID `0x0102`
and the MIDI identity "family" `01 02`). The bootloader checks this and *ignores a
file aimed at a different product* — this is the safety interlock that stops you
flashing a Launchpad image onto a Launchkey. (KernelPicnic saw `02 0F` for the
full-size Launchkey MK3 and `02 11` for the FLKey.)

### METADATA — `F0 00 20 29 00 7C 00 30303034 3631 …`
`30 30 30 34 36 31` is ASCII **"000461"** = the build number. Trailing bytes look
like a date and/or a CRC32 (xkey implements a CRC32 with the ITU V.42 poly, which
is the integrity check the bootloader uses).

### DATA — `F0 00 20 29 00 72 <37 bytes> F7`
Each DATA message carries 37 *encoded* payload bytes. There are ~2750 of them.
Crucially, **DATA records carry no address** — they're concatenated in order
starting at the (out-of-band) load address. That's why finding the load address is
a separate step (see note 05).

### END — `F0 00 20 29 00 73 <last chunk> F7`
The final image is **padded to a boundary with `0xFF`** (erased-flash value). In the
encoding, `0xFF` shows up as `0x7F` bytes near the end of the last records.

## The 7-bit encoding (why bytes look scrambled)
MIDI data bytes can only use 7 bits (the high bit marks status bytes), so binary
firmware must be re-packed into 7-bit-safe bytes. Novation uses a **bit-packer**:
roughly every 8 input bytes become 7 output bytes, sliding the "stolen" high bits
into a carry. `xkey`'s `codec.py` implements both directions (`encoder`/`decoder`).
There's also a simpler `bytes_to_nibbles` scheme (each byte → two 4-bit bytes) used
for small fields. Reading that file is the fastest way to *get* the encoding.

## Decode to raw binary
```
xkey decode firmware/launchkey-mini-mk3_v1.2-build461.syx
# -> firmware/launchkey-mini-mk3_v1.2-build461.syx.bin   (88,088 bytes)
```
`xkey --debug decode …` prints every record it finds (START/METADATA/2750×DATA/END)
— useful to *see* the structure.

## Is it encrypted or signed?
**No encryption.** Confirmed by prior art (`binwalk -E`/`strings`) and by us: the
decoded image is immediately valid Cortex-M code (note 05). The only integrity
check is the **CRC32** in metadata — a checksum, not a signature. Practically: the
bootloader will accept any image with a correct CRC and matching device id. That's
what makes custom firmware feasible (note 08), though a bad flash still bricks to
the bootloader, recoverable via the Octave± DFU entry.
