# 16 — We flashed custom firmware! + the palette is B,G,R (and idx 12 was wrong)

The big milestone: **we successfully flashed modified firmware over MIDI and the device
booted it**, proving the whole pipeline (build → encode → flash → recover) end to end.
Two earlier assumptions turned out wrong, and the hardware told us so.

## Flashing works (and recovers)
`scripts/flash.py` (the reconstruction from notes 14/15) drove a full transfer: START →
METADATA → 2752 DATA (each waited for its `00 72 <count>` ack) → END → `00 73 7F 7F 7F`
complete → device rebooted into the new image. Confirmed by **visible LED changes**.

Two flasher bugs found and fixed along the way:
1. **Don't run it foreground with a short timeout.** The first attempt was killed by a
   150 s Bash timeout at packet ~827/2752 → interrupted transfer → device sat in the
   bootloader and **reverted to the previous firmware** (safe!). Fix: **run in the
   background** (no timeout) and **throttle the per-packet logging** (printing 5500 lines
   was most of the slowdown). With both, a full flash takes well under a minute.
2. Completion check compared a `list` to `bytes` (always false) → it printed a bogus
   "ABORT" *after* the device had already completed. Fixed to `list(b[6:9]) == [0x7F]*3`.

**Recovery is proven twice:** an interrupted/incomplete image is rejected by the
bootloader, which keeps the prior firmware. The SysEx path never bricks.

## The palette is **B, G, R** — not R, G, B
We flashed an all-`7F 00 00` palette expecting red; the device turned **blue** and lit up
buttons that were previously dark. So byte 0 is the **blue** channel. Verified against the
firmware palette itself:

| idx | file bytes | as B,G,R → RGB | meaning |
|---|---|---|---|
| 5  | `00 00 FF` | rgb(255,0,0) | **red**  (standard-palette index 5) |
| 21 | `00 FF 00` | rgb(0,255,0) | **green** |
| 45 | `FF 00 00` | rgb(0,0,255) | **blue** |

So **red = `00 00 7F`** in file order, not `7F 00 00`.

## Consequence: index 12 was never the session colour
Note 11 read index 12's bytes `2F AF FF` as RGB(47,175,255)=cyan. In the real **B,G,R**
order that's RGB(255,175,47) = **orange**. That's why patching index 12 to "red" did
nothing visible to the (cyan) session pads — index 12 is orange and unrelated. The
all-palette flash *did* change the session pads, so the session idle uses **some other
index**, which we're pinning down with a marker flash (`build/launchkey-mini-mk3_v1.2_markers.syx`:
6 candidate cyan/blue indices each painted a distinct colour — the colour the session
pads turn identifies the index).

## Also learned from the all-red flash
Setting the whole palette one colour lit up nearly every button (Launch, Stop/Solo/Mute,
etc.) — so those button LEDs are palette-driven too, off = palette index 0 (black).
Play/Record/Fixed-Chord/Shift/Octave are **white-only** LEDs (not RGB / not palette).

## Firmware vs Components palette indices differ
Components' display-palette index→rgb map (e.g. `cyan: index 10`) does **not** match the
firmware's internal palette (firmware idx 10 = `00 1F 7F` = dark orange-red). Use the
firmware palette bytes directly, decoded as B,G,R.

## Encoding CONFIRMED on hardware + session index FOUND
- **Byte order is B,G,R** (byte0=Blue, byte1=Green, byte2=Red, byte3=pad). Proven by two
  whole-palette flashes: all=`7F 00 00` → device blue (byte0=blue); all=`00 FF 00` →
  device green (byte1=green); red by elimination. So **red = file `00 00 7F`**. Full
  decoded palette saved to `notes/palette-v2-decoded.txt` (standard Novation 128-colour set).
- **Standalone Session-mode idle colour = palette index 42** = stock `7F 2F 00` =
  rgb(0,47,127), a *dim* blue (which is why the "cyan" scans missed it). Found by a
  3-flash binary search (paint all 128 in 6 colour bands by index range → observe which
  band-colour the session pads take → zoom in): band1 green→22-42, band2 magenta→40-42,
  and 40/41 already eliminated by round-1 markers ⇒ **42**.
- Eliminated (NOT the session index): {36,37,40,41,78,91,32,33,48,90,115,116,29,34,38,68,77,92,119}.

## The marker/binary-search method (reusable)
To find which palette index drives any LED: flash images that paint candidate indices
distinct colours (rest left stock), observe which colour the target LED adopts. For an
unknown index, binary-search by painting all 128 in 6 colour *bands* by range; ~3 flashes
pins any index. Colours are encoding-independent as long as they're visually distinct.

## Status / next
- Final patch: index 42 → red `00 00 7F` = `build/launchkey-mini-mk3_v1.2_session-red-FINAL.syx`.
- Flasher: `python scripts/flash.py <file.syx> --go` — run in **background**, press Scene
  Launch ~3 s in, ~40 s. To restore stock: flash `build/stock.bin` re-encoded, or via Components.
- Next ideas: map which indices drive which other LEDs; route-B descriptor writer; other tweaks.
</content>
