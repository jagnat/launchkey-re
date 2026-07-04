    .syntax unified
    .thumb

@ ============================================================================
@ ui_glue — asm shims wiring the ROM into the C payload (mods/c/ui.c).
@ struct ui_state @0x2000F000: +0 magic (0x55AC0DE5), +4 mode, +5 shift_down,
@ +8 frame — layout shared with ui.c, keep in sync.
@ Stock code is compiler-generated, so SP is 8-aligned at every bl; every
@ shim pushes a multiple of 8 bytes before calling C.
@ ============================================================================

@ ---- ui_tap_emit: prologue detour on control_value_emit @0x0800F840 --------
@ (r0=id, r1=value). Call ui_on_press(id, value); nonzero return = SWALLOW:
@ skip the subscriber fan-out entirely and return to the scanner — no stock
@ MIDI/LED/dispatch subscriber sees the event (M2.1). Otherwise replay the 2
@ displaced entry insns (push {r3-r7,lr}; mov r4,r0) and resume @0x0800F844.
@ Swallow return value: stock emit's epilogue (pop {r0,r4-r7,pc}) hands the
@ caller's ORIGINAL r3 back in r0, and control_press_scan feeds that return
@ into j_control_value_emit_4 — so mimic it exactly (mov r0, r3).
    .global ui_tap_emit
    .thumb_func
ui_tap_emit:
    push {r0, r1, r2, r3, ip, lr}
    bl   ui_on_press
    cmp  r0, #0
    pop  {r0, r1, r2, r3, ip, lr}   @ flags survive the pop
    bne  9f
    push {r3, r4, r5, r6, r7, lr}   @ displaced
    mov  r4, r0                     @ displaced
    movw r2, #0xF845                @ 0x0800F844 | thumb
    movt r2, #0x0800
    bx   r2
9:
    mov  r0, r3                     @ stock-identical return quirk
    bx   lr

@ ---- ui_tap_release: prologue detour on control_value_release @0x0800F884 --
@ (r0=id). Displaced entry: push {r4,r5,r6,lr}; mov r4,r0. Resume @0x0800F888.
    .global ui_tap_release
    .thumb_func
ui_tap_release:
    push {r0, r1, r2, lr}
    bl   ui_on_release
    pop  {r0, r1, r2, lr}
    push {r4, r5, r6, lr}           @ displaced
    mov  r4, r0                     @ displaced
    movw r2, #0xF889                @ 0x0800F888 | thumb
    movt r2, #0x0800
    bx   r2

@ ---- ui_dispatch_gate: replaces `bl nullsub_080081d0` @0x0800C742 ----------
@ First call inside control_dispatch's layer-0 handler chain (r0 = control id).
@ Stack at this point = [saved r4][saved lr -> event pump], per the 0x0800C72C
@ prologue (push {r4,lr}; mov r4,r0; bl gate; cmp; mov r0,r4; beq here).
@ mode==0 or struct not yet initialized -> plain return (stock unchanged).
@ mode!=0 -> pop {r4, pc}: unwind control_dispatch's frame and return straight
@ to the pump — the entire stock handler chain is skipped. The shift/settings
@ layer path (branch taken before this slot) stays fully stock, so its layer
@ state can never wedge while our UI is up. r1-r3 are dead here (caller-saved
@ across the bl this replaces).
    .global ui_dispatch_gate
    .thumb_func
ui_dispatch_gate:
    movw r2, #0xF000
    movt r2, #0x2000
    ldr  r3, [r2]                   @ magic
    movw r1, #0x0DE5
    movt r1, #0x55AC
    cmp  r3, r1
    bne  1f
    ldrb r2, [r2, #4]               @ mode
    cbz  r2, 1f
    pop  {r4, pc}                   @ abort stock dispatch
1:
    bx   lr
