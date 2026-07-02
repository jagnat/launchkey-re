#!/usr/bin/env python3
"""Accumulating firmware-mod builder for the Launchkey Mini MK3.

SINGLE SOURCE OF TRUTH. Starts from build/stock.bin and applies EVERY enabled mod
in MODS, so changes stack instead of clobbering each other. Emits:
  build/firmware.bin   — combined patched image
  build/firmware.syx   — flashable (device id patched to 01 02)
and prints a verification report (disassembles every detour + appended block).

Two mod kinds:
  inline  — overwrite bytes at a fixed file offset (data patches, tiny code patches).
            `frm` is asserted against stock first, so a mod can never silently apply
            to the wrong bytes.
  append  — assemble a Thumb asm source (mods/asm/<file>), place it in the erased
            flash sector-4 tail (auto-allocated from IMAGE_END, 4-aligned, stacking),
            and install a 4-byte `b.w` detour overwriting an existing function entry.

Flashing is NOT done here. Flash with:
  .venv/bin/python scripts/flash.py build/firmware.syx --go     (then press Scene Launch)
"""
import os, sys, glob, subprocess, tempfile, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCK = ROOT / "build" / "stock.bin"
OUT_BIN = ROOT / "build" / "firmware.bin"
OUT_SYX = ROOT / "build" / "firmware.syx"
BASE = 0x08008000
BUILD_NO = 461
ASMDIR = ROOT / "mods" / "asm"

# ---------------------------------------------------------------- mod manifest
# Order matters only for append-address allocation; inline/detour application is
# independent (each is asserted against the bytes it expects).
MODS = [
    dict(kind="inline", name="led-palette-42-red",
         desc="Palette index 42 -> red (BGR 00 00 7f); was cyan 7f 2f 00",
         off=0x142F8, frm="7f2f00", to="00007f"),
    dict(kind="inline", name="cc5b-rhythm-clamp-0to10",
         desc="Widen DAW-port CC 0x5b (Rhythm) handler in FUN_0801aaf0 from 1..4 to 1..10 "
              "so external/DAW MIDI can select Euclidean presets 5-10 (also our HW "
              "validation channel). Replaces the tbb identity-switch with a 1..10 clamp.",
         off=0x12C1C,
         frm="781e03280bd8dfe800f002040608012007e0022005e0032003e0042001e000200027",
         to ="0a2f03d8012f01d338460ae00020002700bf00bf00bf00bf00bf00bf00bf00bf00bf"),
    dict(kind="append", name="euclid-rhythm-engine",
         desc="Detour rhythm_decode(FUN_080175b0): keep stock rhythms 0-4. For cfg[3] 5-10 = "
              "Euclidean via euclid_compute, k=cfg[3]-1 n=16 rot=0. cfg[3] set on-device by the "
              "widened Arp Rhythm pad row (pads 0xd/0xe/0xf -> E(4,16)/E(5,16)/E(6,16)).",
         asm="rhythm_decode.s",
         detour_site=0x080175B0, detour_from="70b5294b"),
    dict(kind="inline", name="arp-rhythm-guard-widen",
         desc="Widen arp_rhythm_select(0x0801387c) so the on-device Arp Rhythm pad row accepts "
              "values 5..10 (free pads 0xd/0xe/0xf) not just 0..4. Replaces the compiler's "
              "obfuscated tbb identity-switch with a direct clamp+store (cmp #10 / strb r4,[sp,#3]) "
              "so pressing pad 0xd sets cfg[3]=5 -> Euclidean. Keeps the group-3 store; pads the "
              "old tbb+cases with nops (dead). This is the on-device ENTRY into Euclidean mode.",
         off=0xB88E,
         frm="042cc1600bd8dfe804f0030c1004120000218df80310",
         to ="c1600a2c0bd88df8034000bf00bf00bf00bf00bf00bf"),
    # NOTE: n (pattern length) is driven by the stock Deviate KNOB (cfg[9]) while the Arp
    # button is HELD — no custom hook needed (see notes/34, rhythm_decode.s). The earlier
    # pot-scan hooks (knob_arp_hook.s @ control_value_emit, knob_f204_hook.s @ FUN_0800f204)
    # were a dead end (wrong approach: turned knobs don't reach the arp UNLESS Arp is held)
    # and have been removed.
]

# ---------------------------------------------------------------- toolchain
def find_tool(name):
    hits = sorted(glob.glob(f"/Applications/ArmGNUToolchain/*/arm-none-eabi/bin/{name}"))
    return hits[-1] if hits else name

AS, LD, OBJCOPY, OBJDUMP = (find_tool(t) for t in
    ("arm-none-eabi-as", "arm-none-eabi-ld", "arm-none-eabi-objcopy", "arm-none-eabi-objdump"))

def assemble(asm_path, at_addr):
    """Assemble + link a Thumb asm file at an absolute address; return raw bytes."""
    with tempfile.TemporaryDirectory() as d:
        o, elf, b = d + "/a.o", d + "/a.elf", d + "/a.bin"
        subprocess.run([AS, "-mcpu=cortex-m4", "-mthumb", str(asm_path), "-o", o], check=True)
        subprocess.run([LD, f"-Ttext=0x{at_addr:X}", "-o", elf, o],
                       check=True, stderr=subprocess.DEVNULL)
        subprocess.run([OBJCOPY, "-O", "binary", elf, b], check=True)
        return open(b, "rb").read()

def thumb_bw(pc, target):
    """Encode a Thumb-2 B.W (T4) branch from `pc` to `target` (±16 MB)."""
    off = target - (pc + 4)
    assert off % 2 == 0
    v = (off >> 1) & 0xFFFFFF
    S, I1, I2 = (v >> 23) & 1, (v >> 22) & 1, (v >> 21) & 1
    imm10, imm11 = (v >> 11) & 0x3FF, v & 0x7FF
    J1, J2 = (1 - I1) ^ S, (1 - I2) ^ S
    hw1 = 0xF000 | (S << 10) | imm10
    hw2 = 0x8000 | (J1 << 13) | (1 << 12) | (J2 << 11) | imm11
    return bytes([hw1 & 0xFF, hw1 >> 8, hw2 & 0xFF, hw2 >> 8])

def align4(x):
    return (x + 3) & ~3

def disasm(b, vma):
    with tempfile.TemporaryDirectory() as d:
        f = d + "/x.bin"; open(f, "wb").write(b)
        out = subprocess.run([OBJDUMP, "-D", "-b", "binary", "-m", "arm",
                              "-M", "force-thumb", f"--adjust-vma=0x{vma:X}", f],
                             capture_output=True, text=True).stdout
    return "\n".join(l for l in out.splitlines() if l.strip().startswith(f"{vma:x}".lstrip("0")[:3]) or "\t" in l)

# ---------------------------------------------------------------- encode .syx
def encode_syx(bin_path, syx_path):
    sys.path.insert(0, str(ROOT / "tools" / "xkey"))
    from xkey.cli import encode
    encode(str(bin_path), "launchkey-mk3", BUILD_NO)   # writes <bin>.syx
    tmp = str(bin_path) + ".syx"
    d = bytearray(open(tmp, "rb").read())
    d[6], d[7] = 0x01, 0x02                              # Mini MK3 device id
    open(syx_path, "wb").write(d)
    os.remove(tmp)

# ---------------------------------------------------------------- build
def main():
    stock = bytearray(open(STOCK, "rb").read())
    assert len(stock) % 4 == 0, "stock image not 4-aligned"
    img = bytearray(stock)
    image_end = BASE + len(stock)
    next_addr = align4(image_end)

    print(f"stock: {len(stock)} B, ends 0x{image_end:08X}\n")

    # pass 1: assemble + allocate append blocks
    for m in MODS:
        if m["kind"] == "append":
            m["_addr"] = next_addr
            m["_bytes"] = assemble(ASMDIR / m["asm"], next_addr)
            next_addr = align4(next_addr + len(m["_bytes"]))

    # pass 2: lay down append blocks (padding gaps with 0xFF = erased flash)
    for m in MODS:
        if m["kind"] == "append":
            while BASE + len(img) < m["_addr"]:
                img.append(0xFF)
            assert BASE + len(img) == m["_addr"]
            img += m["_bytes"]
    while len(img) % 4:
        img.append(0xFF)

    # pass 3: inline patches + detours (each asserted against expected bytes)
    report = []
    for m in MODS:
        if m["kind"] == "inline":
            off, frm, to = m["off"], bytes.fromhex(m["frm"]), bytes.fromhex(m["to"])
            assert img[off:off + len(frm)] == frm, \
                f"{m['name']}: expected {frm.hex()} at 0x{off:X}, found {img[off:off+len(frm)].hex()}"
            img[off:off + len(to)] = to
            report.append(f"  [inline] {m['name']:24s} @0x{BASE+off:08X}  {frm.hex()} -> {to.hex()}")
        else:
            site, off = m["detour_site"], m["detour_site"] - BASE
            frm = bytes.fromhex(m["detour_from"])
            assert img[off:off + len(frm)] == frm, \
                f"{m['name']}: detour-site expected {frm.hex()} at 0x{site:X}, found {img[off:off+len(frm)].hex()}"
            img[off:off + 4] = thumb_bw(site, m["_addr"])
            report.append(f"  [append] {m['name']:24s} detour @0x{site:08X} -> 0x{m['_addr']:08X} "
                          f"({len(m['_bytes'])} B)")

    open(OUT_BIN, "wb").write(img)
    encode_syx(OUT_BIN, OUT_SYX)

    print("MODS APPLIED:")
    print("\n".join(report))
    print(f"\noutput: {OUT_BIN.name} ({len(img)} B, +{len(img)-len(stock)} vs stock), "
          f"ends 0x{BASE+len(img):08X}")
    print(f"        {OUT_SYX.name} (flash with scripts/flash.py)")

    # verification dump
    print("\nVERIFY — detours & appended code:")
    for m in MODS:
        if m["kind"] == "append":
            site, off = m["detour_site"], m["detour_site"] - BASE
            print(f"\n  {m['name']} detour @0x{site:08X}:")
            print("   ", disasm(bytes(img[off:off+4]), site).splitlines()[-1])
            a = m["_addr"] - BASE
            print(f"  appended @0x{m['_addr']:08X} ({len(m['_bytes'])} B):")
            for line in disasm(bytes(img[a:a+len(m["_bytes"])]), m["_addr"]).splitlines()[:4]:
                print("   ", line)

if __name__ == "__main__":
    main()
