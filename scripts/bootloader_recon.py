#!/usr/bin/env python3
"""Reversible bootloader recon for Launchkey Mini MK3.

Sends the reboot-to-bootloader command, waits for the device to re-enumerate as
"Launchkey Mini MK3 BL", and captures any hello / version reply. Does NOT start a
firmware transfer (no START/DATA/END), so it never erases or writes flash. Power-cycle
the device afterwards to return to application mode.
"""
import sys, time, mido

# productId for Launchkey Mini MK3 is [2, 11] = 0x02 0x0B (from Components bundle),
# NOT the firmware START device id 01 02. Reboot-to-bootloader request:
REBOOT = [0xF0, 0x00, 0x20, 0x29, 0x00, 0x71, 0x02, 0x0B, 0x00, 0x00, 0xF7]
INQUIRY = [0x7E, 0x7F, 0x06, 0x01]


def hexs(data):
    return " ".join(f"{b:02X}" for b in data)


def find(substr):
    names = set(mido.get_input_names()) | set(mido.get_output_names())
    return sorted(n for n in names if substr.lower() in n.lower())


def main():
    print("Ports before:", find("launchkey") or "(none)")

    # Send reboot to whatever Launchkey output ports exist (harmless if ignored).
    app_outs = [n for n in mido.get_output_names() if "launchkey" in n.lower()]
    for name in app_outs:
        try:
            with mido.open_output(name) as out:
                out.send(mido.Message("sysex", data=REBOOT[1:-1]))
                print(f"  sent reboot-to-bootloader -> {name}")
        except Exception as e:
            print(f"  ! could not send to {name}: {type(e).__name__} {e}")

    # Poll for a bootloader port (or any change) for up to 18 s.
    print(">>> If the device prompts (pads light up), press the SCENE LAUNCH button now. <<<")
    print("Waiting for re-enumeration (up to 18s)...")
    bl = []
    for _ in range(90):
        time.sleep(0.2)
        bl = find("Launchkey Mini MK3 BL")
        if bl:
            break
    if not bl:
        print("RESULT: no 'BL' port appeared. Current Launchkey ports:", find("launchkey") or "(none)")
        print("        (device may not have rebooted, or BL uses a different name)")
        return 1

    print("RESULT: bootloader port(s) detected:", bl)
    time.sleep(0.4)  # let it settle

    in_name = next((n for n in mido.get_input_names() if "BL" in n and "Launchkey Mini MK3" in n), None)
    out_name = next((n for n in mido.get_output_names() if "BL" in n and "Launchkey Mini MK3" in n), None)
    print(f"  BL input : {in_name}\n  BL output: {out_name}")

    if not in_name:
        print("  (no BL input port to listen on)")
        return 0

    with mido.open_input(in_name) as inp:
        # 1) Listen for any spontaneous hello.
        time.sleep(0.6)
        hello = [m for m in inp.iter_pending()]
        print("  spontaneous BL messages:", [hexs(m.bytes()) for m in hello] or "(none)")

        # 2) Non-transactional device inquiry (safe, reads version only).
        if out_name:
            with mido.open_output(out_name) as out:
                out.send(mido.Message("sysex", data=INQUIRY))
                time.sleep(0.5)
                rep = [m for m in inp.iter_pending() if m.type == "sysex"]
                print("  BL inquiry reply:", [hexs(m.bytes()) for m in rep] or "(no reply)")

    print("\nDone. NO transfer was started; flash untouched.")
    print("Power-cycle the device (unplug/replug) to return to application mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
