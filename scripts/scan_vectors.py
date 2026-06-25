#!/usr/bin/env python3
"""Name the Cortex-M vector table: system exceptions (fixed layout) + external IRQs
(from the SVD interrupt map). Emits symbols.tsv lines. Handlers shared by many unused
slots are named Default_Handler (naming them after one IRQ would be wrong).

Vector layout: word[0]=initial SP, word[1]=Reset, ... word[15]=SysTick, word[16+N]=IRQ N.
"""
import os, struct, xml.etree.ElementTree as ET
from collections import Counter

ROOT = os.path.join(os.path.dirname(__file__), "..")
BIN = os.path.join(ROOT, "firmware", "launchkey-mini-mk3_v1.2-build461.syx.bin")
SVD = os.path.join(ROOT, "tools", "svd", "STM32F401.svd")
BASE = 0x08008000

SYS = {1:"Reset_Handler",2:"NMI_Handler",3:"HardFault_Handler",4:"MemManage_Handler",
       5:"BusFault_Handler",6:"UsageFault_Handler",11:"SVC_Handler",12:"DebugMon_Handler",
       14:"PendSV_Handler",15:"SysTick_Handler"}

def irq_map():
    m = {}
    for it in ET.parse(SVD).iter("interrupt"):
        n = it.findtext("name"); v = it.findtext("value")
        if n and v is not None:
            m[int(v)] = n + "_IRQHandler"
    return m

def main():
    data = open(BIN, "rb").read()
    irqs = irq_map()
    nslots = 16 + (max(irqs) + 1 if irqs else 0)
    handlers = {}  # slot -> addr
    for i in range(1, nslots):
        if i * 4 + 4 > len(data):
            break
        w = struct.unpack_from("<I", data, i * 4)[0]
        if w == 0:
            continue
        addr = w & ~1
        if BASE <= addr < BASE + len(data):
            handlers[i] = addr

    # which addresses are shared (Default_Handler-ish)?
    cnt = Counter(handlers.values())
    rows = {}  # addr -> name (first wins for shared)
    for slot, addr in handlers.items():
        if addr in rows:
            continue
        if cnt[addr] > 1:
            rows[addr] = "Default_Handler"
        elif slot in SYS:
            rows[addr] = SYS[slot]
        elif slot >= 16 and (slot - 16) in irqs:
            rows[addr] = irqs[slot - 16]
        else:
            rows[addr] = f"Handler_slot{slot}"

    print(f"# {len(handlers)} vector slots -> {len(rows)} distinct handlers")
    for addr in sorted(rows):
        print(f"0x{addr:08X}\tfunc\t{rows[addr]}")

if __name__ == "__main__":
    main()
