#!/usr/bin/env python3
"""
midi_capture.py — black-box MIDI harness for the Launchkey Mini MK3.

The device is a MIDI source we can drive and observe at millisecond speed with
ZERO flashing and zero risk. This replaces the slow flash->eyeball loop with
send/play -> measure, and turns static RE hypotheses (arp rate table, scale/chord
intervals, velocity curves, SysEx command surface) into measured facts.

Subcommands:
  ports                      list visible MIDI in/out ports
  monitor   [--port P] [--secs N] [--raw]
                             timestamped log of everything the device emits
  send      --port P (--hex "90 3c 7f" | --sysex "00 70")
                             send raw bytes / wrap a SysEx body in F0 00 20 29 .. F7
  arp       [--port P] [--secs N]
                             capture an arp run and measure clocks-per-step
                             (counts 0xF8 between consecutive note-ons) ->
                             reconstructs g_arp_rate_divisors empirically
  sysexscan --port P [--cmds 00-7f] [--prefix "00"] [--wait MS]
                             sweep app SysEx command bytes, log any response ->
                             maps the SysEx dispatcher command table

Everything is a thin wrapper over the helpers below so you can also drive it from
`python -c` for one-off experiments.
"""
import sys, time, argparse
import mido

MFR = [0x00, 0x20, 0x29]  # Novation/Focusrite manufacturer ID
DEFAULT_PORT = "Launchkey Mini MK3 MIDI Port"
DAW_PORT = "Launchkey Mini MK3 DAW Port"


def find_port(names, want):
    """Resolve a substring to a full port name (case-insensitive)."""
    for n in names:
        if want.lower() in n.lower():
            return n
    raise SystemExit(f"port matching {want!r} not found in {names}")


def open_in(want=DEFAULT_PORT):
    return mido.open_input(find_port(mido.get_input_names(), want))


def open_out(want=DEFAULT_PORT):
    return mido.open_output(find_port(mido.get_output_names(), want))


def parse_hex(s):
    return [int(b, 16) for b in s.replace(",", " ").split()]


def cmd_ports(_):
    print("INPUTS (device -> host):")
    for n in mido.get_input_names():
        print("  ", n)
    print("OUTPUTS (host -> device):")
    for n in mido.get_output_names():
        print("  ", n)


def cmd_monitor(a):
    port = find_port(mido.get_input_names(), a.port)
    print(f"# monitoring {port!r} for {a.secs}s — Ctrl-C to stop early")
    t0 = time.monotonic()
    with mido.open_input(port) as inp:
        try:
            while time.monotonic() - t0 < a.secs:
                for msg in inp.iter_pending():
                    dt = time.monotonic() - t0
                    if a.raw:
                        print(f"{dt:8.4f}  {' '.join(f'{b:02x}' for b in msg.bytes())}")
                    else:
                        print(f"{dt:8.4f}  {msg}")
                time.sleep(0.0005)
        except KeyboardInterrupt:
            pass


def cmd_send(a):
    out = open_out(a.port)
    if a.sysex is not None:
        body = parse_hex(a.sysex)
        msg = mido.Message("sysex", data=MFR + body)
    else:
        msg = mido.Message.from_bytes(parse_hex(a.hex))
    print("sending:", " ".join(f"{b:02x}" for b in msg.bytes()))
    out.send(msg)
    out.close()


def cmd_arp(a):
    """Capture a self-clocked arp run and measure clocks (0xF8) between note-ons.

    Per RE note 20 the device emits BOTH its own MIDI clock and the arp note-ons
    out the MIDI port, so clocks-per-step is directly observable: it equals the
    divisor g_arp_rate_divisors[rate*2 + (straight?0:1)] for the selected rate.
    """
    port = find_port(mido.get_input_names(), a.port)
    print(f"# ARP capture on {port!r} for {a.secs}s")
    print("# On the device: enable Arp, HOLD a note, then it streams. Ctrl-C to stop.")
    clocks = 0
    note_clock_marks = []  # clock-count at each note-on
    events = 0
    t0 = time.monotonic()
    with mido.open_input(port) as inp:
        try:
            while time.monotonic() - t0 < a.secs:
                for msg in inp.iter_pending():
                    events += 1
                    if msg.type == "clock":
                        clocks += 1
                    elif msg.type == "note_on" and msg.velocity > 0:
                        note_clock_marks.append((clocks, msg.note, msg.velocity))
                time.sleep(0.0002)
        except KeyboardInterrupt:
            pass
    print(f"# captured {events} msgs, {clocks} clocks, {len(note_clock_marks)} note-ons")
    if len(note_clock_marks) < 2:
        print("# not enough note-ons — make sure Arp is on and a note is held")
        return
    deltas = [b[0] - a_[0] for a_, b in zip(note_clock_marks, note_clock_marks[1:])]
    from collections import Counter
    hist = Counter(deltas)
    print("# clocks-between-note-ons histogram (clocks: count):")
    for k in sorted(hist):
        print(f"#   {k:3d} clocks: {hist[k]}")
    common = hist.most_common(1)[0][0]
    print(f"# => modal clocks/step = {common}  (24 PPQN: 6=1/16, 12=1/8, 3=1/32, 24=1/4 ...)")
    print("# notes (clock_mark, note, vel):")
    for m in note_clock_marks[:32]:
        print(f"#   {m}")


def cmd_sysexscan(a):
    """Sweep SysEx command bytes; log any device response. Maps the command table."""
    out = open_out(a.port)
    inp = open_in(a.port)
    lo, hi = (int(x, 16) for x in a.cmds.split("-"))
    prefix = parse_hex(a.prefix) if a.prefix else []
    wait = a.wait / 1000.0
    print(f"# sweeping SysEx {a.prefix or ''} {lo:02x}..{hi:02x} on {a.port}")
    for c in range(lo, hi + 1):
        # drain stale
        for _ in inp.iter_pending():
            pass
        out.send(mido.Message("sysex", data=MFR + prefix + [c]))
        time.sleep(wait)
        resp = [m for m in inp.iter_pending() if m.type == "sysex"]
        if resp:
            for m in resp:
                b = " ".join(f"{x:02x}" for x in m.bytes())
                print(f"cmd {c:02x} -> {b}")
        else:
            print(f"cmd {c:02x} -> (no response)")
    out.close(); inp.close()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports").set_defaults(func=cmd_ports)

    m = sub.add_parser("monitor"); m.set_defaults(func=cmd_monitor)
    m.add_argument("--port", default=DEFAULT_PORT)
    m.add_argument("--secs", type=float, default=20)
    m.add_argument("--raw", action="store_true")

    s = sub.add_parser("send"); s.set_defaults(func=cmd_send)
    s.add_argument("--port", default=DEFAULT_PORT)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--hex"); g.add_argument("--sysex")

    ar = sub.add_parser("arp"); ar.set_defaults(func=cmd_arp)
    ar.add_argument("--port", default=DEFAULT_PORT)
    ar.add_argument("--secs", type=float, default=15)

    sx = sub.add_parser("sysexscan"); sx.set_defaults(func=cmd_sysexscan)
    sx.add_argument("--port", default=DEFAULT_PORT)
    sx.add_argument("--cmds", default="00-7f")
    sx.add_argument("--prefix", default="")
    sx.add_argument("--wait", type=float, default=60)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
