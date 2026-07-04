    .syntax unified
    .thumb
    .global control_emit_tap

@ ============================================================================
@ control_emit_tap — DIAGNOSTIC (control-id scope, INPUT side v3).
@
@ Prologue detour on control_value_emit @0x0800F840 (b.w installed by build.py
@ overwrites the 4 entry bytes: push {r3-r7,lr} / mov r4,r0). This is the
@ control-surface scanner's PUBLISH seam: every conditioned physical control
@ event arrives here as (r0=id, r1=value) — see re/map/input.md. Per the
@ control-type table @0x0801C7D0, pads are ids 0x00-0x0F (type 3), buttons
@ type 4, strips 0x36/0x37 (type 5), pots 0x80+.
@
@ v2 post-mortem: the old debug byte 0x2000DD37 sits INSIDE live static data
@ (firmware statics extend to ~0x2000E771) and is overwritten by a firmware
@ pad-row writer -> both v1 and v2 scopes read back 8/0 regardless of what the
@ tap stored. v3 moves the debug pair to 0x2000F000 — unreferenced by any code
@ (2 KB above the last static datum, 4 KB below the 0x2000FFF8 init SP).
@
@ Records id @0x2000F000, value low byte @0x2000F001 (rendered on the bottom /
@ top pad rows by page_slot.s), replays the two displaced entry instructions,
@ resumes @0x0800F844. r2/r3 are dead there; r1 (value) is untouched.
@ ============================================================================
control_emit_tap:
    movw r2, #0xF000
    movt r2, #0x2000
    strb r0, [r2]              @ +0 = control id
    strb r1, [r2, #1]          @ +1 = value (low byte)

    push {r3, r4, r5, r6, r7, lr}   @ displaced: original entry push
    mov  r4, r0                     @ displaced: original mov r4, r0

    movw r2, #0xF845           @ 0x0800F844 | 1 — resume original body
    movt r2, #0x0800
    bx   r2
