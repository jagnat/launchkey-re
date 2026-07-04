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
  append  — build sources (Thumb asm and/or freestanding C) into one block placed in
            the erased flash sector-4 tail (auto-allocated from IMAGE_END, 4-aligned,
            stacking), then install one or more 4-byte detours (`b.w` or `bl`) into it.
            Legacy form: asm="file.s" + detour_site/detour_from/detour_call (detour
            targets the block start). New form: srcs=["asm/x.s","c/y.c"] +
            detours=[dict(site=, frm=, sym=, call=False)] — each detour lands on a
            named symbol resolved from the linked block. C payloads must keep ALL
            state in the 0x2000F000 scratch struct: .data/.bss are rejected (nothing
            initializes/loads them in the flash tail).

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
# RULE: when you edit an .s file, update that mod's name/desc in the same change —
# a desc describing an older iteration of the asm is worse than no desc.
# Dead-end asm goes to mods/asm/attic/, with its post-mortem in re/map/.
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
    dict(kind="append", name="ui-layer-m1m2",
         desc="Custom UI layer M1+M2 (first C payload: c/ui.c + asm/ui_glue.s shims). "
              "Shift+pad8 toggles mode 1 = home page (breathing violet grid, pad0 = Euclid "
              "tile placeholder, pad8 = exit->stock). While mode!=0 the dispatch gate aborts "
              "control_dispatch's layer-0 chain (stock UI deaf; shift/settings layer stays "
              "stock). Input = press/release taps on the publish seam. State @0x2000F000. "
              "Known v1 leaks: pads still emit MIDI notes in mode 1 (note path separate).",
         srcs=["asm/ui_glue.s", "c/ui.c"],
         detours=[
             dict(site=0x0800C95A, frm="fbf73bfc", call=True, sym="ui_frame"),
             dict(site=0x0800F840, frm="f8b50446", sym="ui_tap_emit"),
             dict(site=0x0800F884, frm="70b50446", sym="ui_tap_release"),
             dict(site=0x0800C742, frm="fbf745fd", call=True, sym="ui_dispatch_gate"),
         ]),
    # DIAGNOSTIC PAIR (control-id scope v3) — DISABLED 2026-07-03 after it served its
    # purpose (full surface id map measured -> re/map/input.md). Re-enable by moving the
    # two dicts back inside MODS if another id question comes up.
    # v1/v2 post-mortem: both stored to 0x2000DD37, which is INSIDE live firmware
    # statics (they extend to ~0x2000E771) and is overwritten by a pad-row writer -> both
    # scopes read back id&8 regardless of hook layer. v3 moved the debug pair to 0x2000F000
    # (unreferenced RAM: 2 KB above the last static, 4 KB below init SP) and records value.
]

CTLSCOPE_DISABLED = [
    dict(kind="append", name="ctlscope-render",
         desc="DIAGNOSTIC render half of the control-id scope v3. main_task_tick empty slot "
              "@0x0800C95A: every frame, draw debug pair @0x2000F000 — id on the bottom row "
              "(blue, low bit pad 8), value low-byte on the top row (green, low bit pad 0).",
         asm="page_slot.s",
         detour_site=0x0800C95A, detour_from="fbf73bfc", detour_call=True),
    dict(kind="append", name="ctlscope-input",
         desc="DIAGNOSTIC input half v3. Prologue detour on control_value_emit @0x0800F840: "
              "record (id, value-low) into 0x2000F000/1, replay the 2 displaced entry insns, "
              "resume @0x0800F844. Proves the subscriber seam planned as the custom-page "
              "input backbone.",
         asm="emit_tap.s",
         detour_site=0x0800F840, detour_from="f8b50446"),
]
# Dead-end asm lives in mods/asm/attic/ (hello_page.s tracer, custom_page.s v1) —
# post-mortems in re/map/leds.md. n (pattern length) needs no hook: the stock Deviate knob
# writes cfg[9] while Arp is HELD (re/map/arp.md).

# ---------------------------------------------------------------- toolchain
def find_tool(name):
    hits = sorted(glob.glob(f"/Applications/ArmGNUToolchain/*/arm-none-eabi/bin/{name}"))
    return hits[-1] if hits else name

AS, LD, OBJCOPY, OBJDUMP, GCC, NM = (find_tool(t) for t in
    ("arm-none-eabi-as", "arm-none-eabi-ld", "arm-none-eabi-objcopy", "arm-none-eabi-objdump",
     "arm-none-eabi-gcc", "arm-none-eabi-nm"))

CFLAGS = ["-mcpu=cortex-m4", "-mthumb", "-Os", "-ffreestanding", "-fno-builtin",
          "-nostdlib", "-fomit-frame-pointer", "-fno-common", "-Wall", "-Werror"]

def build_block(srcs, at_addr):
    """Assemble (.s) / compile (.c) sources, link the block at an absolute address.
    Returns (raw bytes, {symbol: address}). Rejects .data/.bss (see module docstring)."""
    with tempfile.TemporaryDirectory() as d:
        objs = []
        for i, s in enumerate(srcs):
            src, o = ROOT / "mods" / s, f"{d}/{i}.o"
            if s.endswith(".c"):
                subprocess.run([GCC, *CFLAGS, "-c", str(src), "-o", o], check=True)
            else:
                subprocess.run([AS, "-mcpu=cortex-m4", "-mthumb", str(src), "-o", o], check=True)
            objs.append(o)
        elf, b = d + "/a.elf", d + "/a.bin"
        # -n: don't page-align sections (keeps .rodata packed right after .text)
        subprocess.run([LD, "-n", f"-Ttext=0x{at_addr:X}", "-o", elf] + objs,
                       check=True, stderr=subprocess.DEVNULL)
        for ln in subprocess.run([OBJDUMP, "-h", elf], capture_output=True, text=True,
                                 check=True).stdout.splitlines():
            p = ln.split()
            if len(p) > 3 and p[1] in (".data", ".bss") and int(p[2], 16):
                raise SystemExit(f"append block has non-empty {p[1]} ({int(p[2],16)} B) — "
                                 "keep all mod state in the 0x2000F000 scratch struct")
        syms = {}
        for ln in subprocess.run([NM, elf], capture_output=True, text=True,
                                 check=True).stdout.splitlines():
            p = ln.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        subprocess.run([OBJCOPY, "-O", "binary", elf, b], check=True)
        return open(b, "rb").read(), syms

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

def thumb_bl(pc, target):
    """Encode a Thumb-2 BL (T1) from `pc` to `target`. Same as B.W but sets the
    link bit (hw2 bit14) so lr is written — used to redirect an existing `bl`
    call-site to appended code while still returning into the caller."""
    b = bytearray(thumb_bw(pc, target))
    b[3] |= 0x40                                          # hw2 |= 0x4000 (link)
    return bytes(b)

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

    # pass 1: build + allocate append blocks (normalize legacy single-detour form)
    for m in MODS:
        if m["kind"] == "append":
            m["_srcs"] = m.get("srcs") or ["asm/" + m["asm"]]
            m["_detours"] = m.get("detours") or [dict(site=m["detour_site"],
                                                      frm=m["detour_from"],
                                                      call=m.get("detour_call", False),
                                                      sym=None)]
            m["_addr"] = next_addr
            m["_bytes"], m["_syms"] = build_block(m["_srcs"], next_addr)
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
            for dt in m["_detours"]:
                site, off = dt["site"], dt["site"] - BASE
                frm = bytes.fromhex(dt["frm"])
                assert img[off:off + len(frm)] == frm, \
                    f"{m['name']}: detour-site expected {frm.hex()} at 0x{site:X}, found {img[off:off+len(frm)].hex()}"
                if dt.get("sym"):
                    assert dt["sym"] in m["_syms"], f"{m['name']}: symbol {dt['sym']} not in block"
                    target = m["_syms"][dt["sym"]]
                else:
                    target = m["_addr"]
                enc = thumb_bl if dt.get("call") else thumb_bw
                img[off:off + 4] = enc(site, target)
                kind = "bl-call" if dt.get("call") else "b.w"
                tgt = f"{dt['sym']}@" if dt.get("sym") else ""
                report.append(f"  [append] {m['name']:24s} {kind} @0x{site:08X} -> {tgt}0x{target:08X}")
            report.append(f"  [append] {m['name']:24s} block @0x{m['_addr']:08X} ({len(m['_bytes'])} B)")

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
            print(f"\n  {m['name']}:")
            for dt in m["_detours"]:
                site, off = dt["site"], dt["site"] - BASE
                print("   ", disasm(bytes(img[off:off+4]), site).splitlines()[-1])
            a = m["_addr"] - BASE
            print(f"  appended @0x{m['_addr']:08X} ({len(m['_bytes'])} B):")
            for line in disasm(bytes(img[a:a+len(m["_bytes"])]), m["_addr"]).splitlines()[:4]:
                print("   ", line)

if __name__ == "__main__":
    main()
