    .syntax unified
    .thumb
    .global custom_page_slot_render

@ ============================================================================
@ custom_page_slot_render — DIAGNOSTIC (control-id scope, RENDER side).
@
@ Hooked into main_task_tick's empty slot `bl nullsub_080081d4` @0x0800C95A.
@ EVERY frame (no gate — the readout must be visible at standalone idle, where
@ the future page toggle will live), draw the debug byte @0x2000DD37 (last
@ control id published through control_value_emit, written by emit_tap.s) as an
@ 8-bit BINARY readout on the bottom pad row: pad (8+i) lit blue if bit i of
@ the id is set, else off. Low bit on pad 8, high bit on pad 0xf. Boot state
@ (byte=0) renders the row dark — expected for a diagnostic.
@ Uses direct layer (led_attr_set_direct sets 0x80 so it shows over palette).
@ Preserve r4-r7 (main_task_tick reuses r4/r5); value held in r6, bit index in r7.
@ ============================================================================
custom_page_slot_render:
    push {r4, r5, r6, r7, lr}

    movw r4, #0xDD37           @ debug byte
    movt r4, #0x2000
    ldrb r6, [r4]              @ r6 = id to display

    movw r4, #0xBB6D           @ led_attr_set_direct @0x0800BB6C | thumb
    movt r4, #0x0800
    movw r5, #0xBB51           @ led_set_color       @0x0800BB50 | thumb
    movt r5, #0x0800
    movs r7, #0                @ bit index 0..7
2:
    add  r0, r7, #8            @ pad = 8 + i (bottom row)
    movs r1, #0
    blx  r4                    @ led_attr_set_direct(pad, 0) -> direct bit
    add  r0, r7, #8            @ pad again (r0 clobbered by the call)
    lsr  r2, r6, r7            @ r2 = id >> i
    and  r2, r2, #1            @ bit i
    cbz  r2, 3f
    movw r1, #0x00FF           @ bit set -> blue
    b    4f
3:
    movs r1, #0                @ bit clear -> off
4:
    blx  r5                    @ led_set_color(pad, color)
    adds r7, r7, #1
    cmp  r7, #8
    blo  2b
1:
    pop  {r4, r5, r6, r7, pc}
