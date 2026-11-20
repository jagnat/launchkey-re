#!/usr/bin/env python3
"""Download stock Launchkey Mini MK3 v1.2 (build 461) firmware from Novation and
decode it to build/stock.bin, the input mods/build.py patches.

Needs the xkey source clone at tools/xkey (see README).
"""
import hashlib, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "https://components.novationmusic.com/api/v2/firmwares/159/file"
SYX = ROOT / "firmware" / "launchkey-mini-mk3_v1.2-build461.syx"
BIN = ROOT / "build" / "stock.bin"
SYX_SHA256 = "0f326624a1ec603097b5f61d68998f42d1f0f8af39c4e444fd2706a75869dfa6"
BIN_SHA256 = "09d8f439121400afc6c806a9d568346201e4d45be85383fe144bc700886329f7"


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    SYX.parent.mkdir(exist_ok=True)
    BIN.parent.mkdir(exist_ok=True)
    if not SYX.exists():
        print(f"downloading {URL}")
        subprocess.run(["curl", "-fsSL", "-o", str(SYX), URL], check=True)
    if sha256(SYX) != SYX_SHA256:
        sys.exit(f"{SYX}: SHA-256 mismatch — not stock build 461")

    sys.path.insert(0, str(ROOT / "tools" / "xkey"))
    from xkey.cli import decode
    if decode(str(SYX)) != 0:
        sys.exit("xkey decode failed")
    out = pathlib.Path(f"{SYX}.bin")
    if sha256(out) != BIN_SHA256:
        sys.exit(f"{out}: decoded image SHA-256 mismatch")
    shutil.copyfile(out, BIN)
    print(f"ok: {BIN} ({BIN.stat().st_size} B)")


if __name__ == "__main__":
    main()
