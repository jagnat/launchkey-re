#!/usr/bin/env python3
"""Probe the Launchkey: list MIDI ports + send Universal Device Inquiry."""
import time, sys
import mido

print("=== Output ports ===")
for p in mido.get_output_names():
    print("  ", p)
print("=== Input ports ===")
for p in mido.get_input_names():
    print("  ", p)

def pick(names, want):
    for n in names:
        if want.lower() in n.lower():
            return n
    return None

outs, ins = mido.get_output_names(), mido.get_input_names()
# Universal Non-Realtime Device Inquiry: F0 7E 7F 06 01 F7
inquiry = mido.Message('sysex', data=[0x7E, 0x7F, 0x06, 0x01])

# Try every output port, listen on every input port for ~0.4s each.
for oname in outs:
    try:
        out = mido.open_output(oname)
    except Exception as e:
        print(f"!! cannot open out {oname}: {e}"); continue
    openins = []
    for iname in ins:
        try:
            openins.append((iname, mido.open_input(iname)))
        except Exception:
            pass
    print(f"\n>>> sending Device Inquiry on: {oname}")
    out.send(inquiry)
    t0 = time.time()
    got = False
    while time.time() - t0 < 0.5:
        for iname, inp in openins:
            for msg in inp.iter_pending():
                if msg.type == 'sysex':
                    print(f"    <<< [{iname}] {' '.join(f'{b:02X}' for b in msg.bytes())}")
                    got = True
        time.sleep(0.01)
    if not got:
        print("    (no sysex reply)")
    out.close()
    for _, inp in openins:
        inp.close()
