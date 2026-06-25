#!/usr/bin/env python3
"""Capture device->host MIDI while Novation Components runs a real firmware update.

Continuously discovers Launchkey ports (including the 'Launchkey Mini MK3 BL' port that
appears when the device reboots into the bootloader), opens each, and logs every message
with a timestamp + source port. Clock (F8) and active-sensing (FE) are filtered out to
keep the log readable; SysEx and everything else is kept verbatim.

Run this (background), then in Novation Components run the firmware update for the
device. The log captures the bootloader hello + the per-packet request/ACK handshake
(device->host) that we need to replay our patched image. Stops after --secs (default 300)
or on Ctrl-C. Read-only: this script never sends anything.
"""
import sys, time, mido

LOG = "build/update_capture.log"
NOISE = {0xF8, 0xFE}  # clock, active-sensing
hexs = lambda d: " ".join(f"{b:02X}" for b in d)


def lk_inputs():
    return [n for n in mido.get_input_names() if "launchkey" in n.lower()]


def main(secs=300):
    t0 = time.time()
    open_ports = {}   # name -> input port
    known = set()
    with open(LOG, "w") as log:
        def emit(line):
            stamp = f"{time.time()-t0:7.2f}s"
            print(stamp, line); log.write(f"{stamp} {line}\n"); log.flush()

        emit("CAPTURE START. Now run the firmware update in Novation Components.")
        emit(f"initial LK inputs: {lk_inputs()}")
        while time.time() - t0 < secs:
            # (re)discover ports — BL port appears on reboot, app ports vanish/return.
            cur = set(lk_inputs())
            for n in cur - known:
                emit(f"PORT + appeared: {n}")
                try:
                    open_ports[n] = mido.open_input(n)
                except Exception as e:
                    emit(f"  (could not open {n}: {type(e).__name__} {e})")
            for n in known - cur:
                emit(f"PORT - vanished: {n}")
                p = open_ports.pop(n, None)
                if p:
                    try: p.close()
                    except Exception: pass
            known = cur

            for n, p in list(open_ports.items()):
                try:
                    for m in p.iter_pending():
                        b = m.bytes()
                        if len(b) == 1 and b[0] in NOISE:
                            continue
                        emit(f"{n}: {hexs(b)}")
                except (OSError, IOError) as e:
                    emit(f"  (read error on {n}: {e})")
            time.sleep(0.02)
        emit("CAPTURE END.")
    for p in open_ports.values():
        try: p.close()
        except Exception: pass


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
