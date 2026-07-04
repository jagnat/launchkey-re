    .syntax unified
    .thumb
    .global custom_page_slot_render

@ ============================================================================
@ custom_page_slot_render — DIAGNOSTIC (control-id scope, RENDER side v3).
@
@ Hooked into main_task_tick's empty slot `bl nullsub_080081d4` @0x0800C95A.
@ Every frame, render the debug pair @0x2000F000 (written by emit_tap.s):
@   +0 last control id    -> BOTTOM pad row, blue bits  (low bit on pad 8)
@   +1 last value (low 8) -> TOP pad row,   green bits  (low bit on pad 0)
@ Un-gated: the readout must work at standalone idle. Boot state (0,0) renders
@ both rows dark — expected for a diagnostic.
@ Uses direct layer (led_attr_set_direct sets 0x80 so it shows over palette).
@ Preserve r4-r7 (main_task_tick reuses r4/r5). r6 = value<<8|id, r7 = bit 0..15.
@ ============================================================================
custom_page_slot_render:
    push {r4, r5, r6, r7, lr}

    movw r4, #0xF000           @ debug pair
    movt r4, #0x2000
    ldrh r6, [r4]              @ r6 = value<<8 | id

    movw r4, #0xBB6D           @ led_attr_set_direct @0x0800BB6C | thumb
    movt r4, #0x0800
    movw r5, #0xBB51           @ led_set_color       @0x0800BB50 | thumb
    movt r5, #0x0800
    movs r7, #0                @ bit 0..7 = id -> pads 8..0xf; 8..15 = value -> pads 0..7
2:
    bl   pad_of                @ r0 = pad for bit r7
    movs r1, #0
    blx  r4                    @ led_attr_set_direct(pad, 0) -> direct bit
    bl   pad_of                @ pad again (r0 clobbered by the call)
    lsr  r2, r6, r7
    ands r2, r2, #1            @ bit r7 of value<<8|id
    beq  6f
    cmp  r7, #8
    blt  4f
    movw r1, #0xFF00           @ value bit set -> green
    b    7f
4:
    movw r1, #0x00FF           @ id bit set -> blue
    b    7f
6:
    movs r1, #0                @ bit clear -> off
7:
    blx  r5                    @ led_set_color(pad, color)
    adds r7, r7, #1
    cmp  r7, #16
    blo  2b
    pop  {r4, r5, r6, r7, pc}

pad_of:                        @ r0 = (r7 < 8) ? r7 + 8 : r7 - 8
    cmp  r7, #8
    ite  lt
    addlt r0, r7, #8
    subge r0, r7, #8
    bx   lr
