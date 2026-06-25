#!/usr/bin/env python3
"""Instrumented bootloader-entry attempt: enable DAW mode, then send reboot.

Logs every MIDI port change and every device->host message during a watch window,
so we can see exactly how the device reacts. Read-only w.r.t. flash: only sends the
DAW-mode-enable note and the reboot request (no firmware DATA), so nothing is written.
"""
import time, mido

hexs = lambda d: " ".join(f"{b:02X}" for b in d)
DAW_ON = mido.Message("note_on", channel=15, note=0x0C, velocity=0x7F)   # 9F 0C 7F
REBOOTS = {
    "productId 02 0B": [0x00, 0x20, 0x29, 0x00, 0x71, 0x02, 0x0B, 0x00, 0x00],
    "fw-id   01 02":   [0x00, 0x20, 0x29, 0x00, 0x71, 0x01, 0x02, 0x00, 0x00],
}


def ports():
    return sorted(set(mido.get_input_names()) | set(mido.get_output_names()))


def lk_out(substr):
    return next((n for n in mido.get_output_names() if substr in n and "launchkey" in n.lower()), None)


def main():
    daw_out = lk_out("DAW")
    midi_out = lk_out("MIDI Port")
    print("DAW out:", daw_out, "| MIDI out:", midi_out)

    # Open inputs to capture any device replies throughout.
    inputs = []
    for n in mido.get_input_names():
        if "launchkey" in n.lower():
            try: inputs.append((n, mido.open_input(n)))
            except Exception as e: print("  cant open", n, e)

    # 1) enable DAW / InControl mode.
    if daw_out:
        with mido.open_output(daw_out) as o:
            o.send(DAW_ON)
        print("sent DAW-mode enable (9F 0C 7F) -> DAW port  (pads should light up)")
    time.sleep(0.6)

    # 2) send each reboot variant to both DAW and MIDI outputs.
    for label, data in REBOOTS.items():
        for tgt in (daw_out, midi_out):
            if not tgt: continue
            with mido.open_output(tgt) as o:
                o.send(mido.Message("sysex", data=data))
            print(f"sent reboot [{label}] -> {tgt}")
        time.sleep(0.4)

    # 3) watch 15s: log port changes + any device replies.
    print(">>> If the device prompts, press SCENE LAUNCH. Watching 15s... <<<")
    base = ports()
    start = time.time()
    while time.time() - start < 15:
        time.sleep(0.25)
        now = ports()
        if now != base:
            print(f"  [{time.time()-start:4.1f}s] PORT CHANGE -> {now}")
            base = now
            if any("BL" in p for p in now):
                print("  *** BOOTLOADER PORT APPEARED ***")
                break
        for n, inp in inputs:
            for m in inp.iter_pending():
                print(f"  [{time.time()-start:4.1f}s] {n}: {hexs(m.bytes())}")

    for _, inp in inputs:
        inp.close()
    print("Done. No firmware DATA sent; flash untouched.")


if __name__ == "__main__":
    main()
