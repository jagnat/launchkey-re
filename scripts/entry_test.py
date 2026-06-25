#!/usr/bin/env python3
"""Safe bootloader-ENTRY test for the (now v1.2) Launchkey Mini MK3.

Sends only the reboot-to-bootloader request and listens for the device to announce
itself as a bootloader (serial 00 42 / version 00 70), the way Components' update did.
NO firmware DATA is sent, so nothing is written/erased. The bootloader uses the SAME
MIDI Port on this firmware (note 14), so we listen there.
"""
import time, mido

hexs = lambda d: " ".join(f"{b:02X}" for b in d)
NOISE = {0xF8, 0xFE}
# Two candidate ids: productId 02 0B and firmware id 01 02.
REBOOTS = [("productId 02 0B", [0x00,0x20,0x29,0x00,0x71,0x02,0x0B,0x00,0x00]),
           ("fw-id   01 02",   [0x00,0x20,0x29,0x00,0x71,0x01,0x02,0x00,0x00])]


def lk(kind, substr):
    fn = mido.get_input_names if kind == "in" else mido.get_output_names
    return next((n for n in fn() if substr in n and "launchkey" in n.lower()), None)


def main():
    out_name = lk("out", "MIDI Port")
    in_name = lk("in", "MIDI Port")
    print("MIDI out:", out_name, "| MIDI in:", in_name)
    inp = mido.open_input(in_name) if in_name else None

    for label, data in REBOOTS:
        with mido.open_output(out_name) as o:
            o.send(mido.Message("sysex", data=data))
        print(f"sent reboot [{label}] -> {out_name}")
        # Listen 8s for a bootloader announcement before trying the other id.
        print(">>> If the device prompts, press SCENE LAUNCH now. <<<")
        t0 = time.time()
        announced = False
        while time.time() - t0 < 8:
            if inp:
                for m in inp.iter_pending():
                    b = m.bytes()
                    if len(b) == 1 and b[0] in NOISE:
                        continue
                    print(f"  [{time.time()-t0:4.1f}s] {hexs(b)}")
                    if len(b) >= 6 and b[4] == 0x00 and b[5] in (0x42, 0x70, 0x72, 0x73):
                        announced = True
            if any("BL" in n for n in mido.get_input_names()):
                print("  *** a BL port appeared ***"); announced = True
            time.sleep(0.05)
        if announced:
            print(f"  >>> DEVICE RESPONDED to [{label}] — bootloader entry likely works! <<<")
            break
        print(f"  (no bootloader response to [{label}])")

    if inp: inp.close()
    print("Done. No firmware data sent; flash untouched.")


if __name__ == "__main__":
    main()
