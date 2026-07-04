    .syntax unified
    .thumb
    .global arp_pad6_toggle

@ ============================================================================
@ arp_pad6_toggle — DIAGNOSTIC (pad-id scope, INPUT side).
@
@ Hooked at control_dispatch's `bl arp_control_handler` @0x0800C778 (thumb_bl, returns
@ into control_dispatch @0x0800C77C). On entry r0 = param_1 = control/pad id.
@ While the arp panel is active (*0x2000e628 != 0), record the id of every control
@ event into a debug byte @0x2000DD37; the render hook draws it in binary on the
@ bottom pad row. This tells us the actual id of each arp-panel pad (and whether the
@ unused top pads emit events at all). Then call the real arp_control_handler(param_1).
@ Uses only r0-r3 (r0 preserved). arp_control_handler is AAPCS.
@ ============================================================================
arp_pad6_toggle:
    push {lr}

    movw r2, #0xE628           @ arp panel state base (byte +0 = panel active)
    movt r2, #0x2000
    ldrb r3, [r2]
    cbz  r3, 1f                @ panel not active -> passthrough
    movw r2, #0xDD37           @ debug byte addr
    movt r2, #0x2000
    strb r0, [r2]              @ record this event's id (param_1)
1:
    movw r2, #0x391D           @ arp_control_handler @0x0801391C | thumb
    movt r2, #0x0801
    blx  r2                    @ r0 still = param_1
    pop  {pc}
