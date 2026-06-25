#!/usr/bin/env python3
"""Watch for the Launchkey Mini MK3 bootloader port and capture its hello/version.

Run this, then put the device into bootloader mode (unplug, hold Octave+ AND Octave-,
replug while holding). When the 'Launchkey Mini MK3 BL' port appears we capture any
spontaneous message + a device-inquiry reply. Read-only: no transfer is started.
"""
import sys, time, mido

INQUIRY = [0x7E, 0x7F, 0x06, 0x01]
hexs = lambda d: " ".join(f"{b:02X}" for b in d)


def find(substr):
    names = set(mido.get_input_names()) | set(mido.get_output_names())
    return sorted(n for n in names if substr.lower() in n.lower())


def main(window=60):
    print(f"Watching for bootloader port for {window}s...")
    print("NOW: unplug the device, hold Octave+ AND Octave-, and replug while holding.")
    start = time.time()
    bl = []
    while time.time() - start < window:
        time.sleep(0.3)
        bl = find("Launchkey Mini MK3 BL")
        if bl:
            break
        # also report any unexpected new ports
    if not bl:
        print("RESULT: no bootloader port appeared. Current:", find("launchkey") or "(none)")
        return 1

    print("RESULT: bootloader port detected:", bl)
    time.sleep(0.5)
    in_name = next((n for n in mido.get_input_names() if "BL" in n and "Launchkey Mini MK3" in n), None)
    out_name = next((n for n in mido.get_output_names() if "BL" in n and "Launchkey Mini MK3" in n), None)
    print("  BL in :", in_name, "\n  BL out:", out_name)
    if in_name:
        with mido.open_input(in_name) as inp:
            time.sleep(0.6)
            print("  spontaneous:", [hexs(m.bytes()) for m in inp.iter_pending()] or "(none)")
            if out_name:
                with mido.open_output(out_name) as out:
                    out.send(mido.Message("sysex", data=INQUIRY))
                    time.sleep(0.5)
                    print("  inquiry reply:", [hexs(m.bytes()) for m in inp.iter_pending() if m.type == "sysex"] or "(none)")
    print("\nNO transfer started; flash untouched. Power-cycle to return to app mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 60))
