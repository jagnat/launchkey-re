    .syntax unified
    .thumb
    .global control_emit_tap

@ ============================================================================
@ control_emit_tap — DIAGNOSTIC (control-id scope, INPUT side v2).
@
@ Prologue detour on control_value_emit @0x0800F840 (b.w installed by build.py
@ overwrites the 4 entry bytes: push {r3-r7,lr} / mov r4,r0). This is the
@ control-surface scanner's PUBLISH seam: every conditioned physical control
@ event (pads/keys via control_velocity_scan, pots|0x80 via pot_scan, strip
@ 0x36 via pitchstrip_scan) arrives here as (r0=id, r1=value) — asm-verified
@ (r4=id/r5=value fan-out to the subscriber table @0x2000E3B0, and pot_scan
@ decompiles as control_value_emit(idx|0x80, value)).
@
@ Record id into the debug byte @0x2000DD37 (rendered in binary on the bottom
@ pad row by page_slot.s), replay the two displaced entry instructions, and
@ continue at 0x0800F844. r2/r3 are dead at that point (loop re-derives them);
@ r1 (value) is untouched.
@
@ This seam is the planned INPUT backbone for the custom page/menu system —
@ this diagnostic doubles as its hardware proof.
@ ============================================================================
control_emit_tap:
    movw r2, #0xDD37
    movt r2, #0x2000
    strb r0, [r2]              @ debug byte = control id

    push {r3, r4, r5, r6, r7, lr}   @ displaced: original entry push
    mov  r4, r0                     @ displaced: original mov r4, r0

    movw r2, #0xF845           @ 0x0800F844 | 1 — resume original body
    movt r2, #0x0800
    bx   r2
