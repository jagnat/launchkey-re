#!/usr/bin/env python3
"""Flash a Launchkey Mini MK3 firmware .syx over MIDI, reconstructed from Components.

Implements the ACK-driven protocol decoded in notes 14 & 15:
  - send START to the MIDI port to trigger reboot-to-bootloader (+ user presses Scene Launch)
  - send START again, then METADATA back-to-back (no wait)
  - for each DATA packet: send, then wait for the device's `00 72 <count>` ACK before the next
  - send END, wait for the `00 73` completion marker

SAFETY: dry-run by default (parses + prints the plan, sends nothing). With --go it streams,
but it will NOT send any DATA packet until it has seen the first `00 72` ACK — so if the
device never enters the bootloader, nothing past START/METADATA (which carry no firmware
bytes) is ever sent. Recovery if a transfer fails: reflash via Novation Components; the
SysEx path never writes the bootloader region (note 08).
"""
import sys, time, argparse, mido

NOV = bytes([0x00, 0x20, 0x29])
PORT_SUBSTR = "MIDI Port"
CMD = {0x71: "START", 0x7C: "METADATA", 0x72: "DATA", 0x73: "END"}


def parse_syx(path):
    raw = open(path, "rb").read()
    msgs, i = [], 0
    while i < len(raw):
        if raw[i] != 0xF0:
            i += 1; continue
        j = raw.index(0xF7, i)
        msgs.append(raw[i:j + 1])
        i = j + 1
    return msgs


def is_nov(m):
    return len(m) >= 6 and m[0] == 0xF0 and bytes(m[1:4]) == NOV


def cmd_of(m):
    return m[5] if is_nov(m) else None


def find_port(getter):
    return next((n for n in getter() if PORT_SUBSTR in n and "launchkey" in n.lower()), None)


def summarize(msgs):
    from collections import Counter
    c = Counter(CMD.get(cmd_of(m), f"?{cmd_of(m)}") for m in msgs)
    return dict(c)


def flash(msgs, go, entry_timeout=30.0, ack_timeout=8.0):
    si = msgs
    n = len(si)
    send_info_header = True  # listenForDeviceStatusReport is false for LK Mini MK3
    out_name, in_name = find_port(mido.get_output_names), find_port(mido.get_input_names)
    print(f"out: {out_name}\nin : {in_name}")
    if not (out_name and in_name):
        print("ERROR: MIDI Port not found."); return 1

    out = mido.open_output(out_name)
    inp = mido.open_input(in_name)

    def send(idx):
        m = si[idx]
        out.send(mido.Message("sysex", data=list(m[1:-1])))
        c = cmd_of(m)
        if c != 0x72 or idx % 250 == 0:   # throttle DATA logging (it dominates the runtime)
            print(f"  -> [{idx}] {CMD.get(c, '?')} ({len(m)} B)", flush=True)

    # 1) trigger reboot-to-bootloader
    print("\n[1] sending START to trigger bootloader entry ...")
    send(0)
    print("    >>> PRESS THE SCENE LAUNCH BUTTON on the device now (within ~13s). <<<")

    # 2) transfer, mirroring #Ii: send packet, recurse over the METADATA header, else wait.
    mi = 0
    state = {"xi": -1, "sent_data": False, "done": False, "await": False}

    def send_next():
        nonlocal mi
        if mi >= n:
            return
        idx = mi; mi += 1
        send(idx)
        if cmd_of(si[idx]) == 0x72:
            state["sent_data"] = True
        # if the NEXT packet is the METADATA header, send it immediately (no wait)
        if mi < n and cmd_of(si[mi]) == 0x7C and send_info_header:
            send_next(); return
        if cmd_of(si[idx]) != 0x73 and mi != n:
            state["await"] = True       # wait for an ACK before the next
        else:
            state["await"] = False      # END / last -> wait for completion

    print("\n[2] starting transfer (START + METADATA, then ACK-driven DATA) ...")
    send_next()  # sends START again + METADATA, then waits for ack #1

    t_last = time.time()
    while not state["done"]:
        now = time.time()
        # safety: abort before any DATA if the bootloader never acks
        if not state["sent_data"] and state["xi"] < 0 and now - t_last > entry_timeout:
            print("\nABORT: no ACK within %.0fs — device did not enter bootloader. "
                  "No DATA was sent; flash untouched." % entry_timeout)
            break
        if state["sent_data"] and now - t_last > ack_timeout:
            print("\nABORT: ACK timeout mid-transfer. Device left in bootloader — "
                  "reflash via Components to recover."); break
        for m in inp.iter_pending():
            b = m.bytes()
            if not is_nov(b):
                continue
            c = b[5]
            if c == 0x72 and len(b) == 10:                # DATA ack
                p = b[6:9]
                count = p[0] + (p[1] << 7) + (p[2] << 14)
                if count > state["xi"] or count == 0:
                    state["xi"] = count; t_last = time.time()
                    if count % 250 == 0 or count == 1:
                        print(f"  <- ACK {count}/{n - 3}", flush=True)
                    send_next()
            elif c == 0x73 and len(b) == 10:              # status / completion
                print(f"  <- STATUS/END {b[6]:02X} {b[7]:02X} {b[8]:02X}")
                if list(b[6:9]) == [0x7F, 0x7F, 0x7F]:    # 00 73 7F 7F 7F = complete
                    print("\nTRANSFER COMPLETE — device should reboot into the new firmware.")
                    state["done"] = True
        time.sleep(0.005)

    inp.close(); out.close()
    return 0 if state["done"] else 1


def main():
    ap = argparse.ArgumentParser(description="Flash a Launchkey Mini MK3 firmware .syx.")
    ap.add_argument("syx", help="path to the .syx to flash")
    ap.add_argument("--go", action="store_true", help="actually stream (default: dry-run)")
    a = ap.parse_args()

    msgs = parse_syx(a.syx)
    print(f"parsed {len(msgs)} SysEx messages from {a.syx}")
    print("breakdown:", summarize(msgs))
    if cmd_of(msgs[0]) != 0x71 or cmd_of(msgs[-1]) != 0x73:
        print("WARNING: expected START first and END last — check the file.")
    if not a.go:
        print("\nDRY-RUN (no MIDI sent). Re-run with --go to flash, with the device "
              "connected and ready to press Scene Launch.")
        return 0
    return flash(msgs, go=True)


if __name__ == "__main__":
    sys.exit(main())
