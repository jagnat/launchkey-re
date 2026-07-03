    .syntax unified
    .thumb
    .global custom_page_tick

@ ============================================================================
@ custom_page_tick — v2 gated custom pad-page (RENDER, precedence-winning).
@
@ Owns the entire pad grid whenever the arp is OFF, i.e. the Arp button is the
@ page toggle: arp off -> our page; arp on -> the stock arp page (we yield).
@
@ Precedence: the stock idle/session fill (FUN_08013dd8->FUN_08013cc2, 16 pads)
@ runs at render slot 8; painting from the EARLY hook nullsub_080081d4 (slot 5)
@ lost to it. So we hook the LAST render call instead — `bl arp_3474` @0x0800C984
@ (the final slot in main_task_tick's per-tick render chain). We call the stock
@ arp_3474 first (preserve its behaviour), then paint OURS last -> nothing
@ overwrites us. No new RAM (gate = arp_get_state, a stock getter readable here).
@
@ Entry (reached by BL replacing `bl arp_3474`):
@   r0 = tick (set by `mov r0,r4` @0x0800C982, arp_3474's arg)  — pass through
@   lr = 0x0800C988 (return into main_task_tick)
@ main_task_tick does `mov r0,r4` @0x0800C988 BEFORE reloading r4 from the stack,
@ so r4 must equal the entry tick on return -> we save/restore r4 (and r5).
@ led_set_color / arp_* are AAPCS (preserve r4-r11), so our held addrs survive.
@
@ Pattern: top row (idx 0..7) green 0x00FF00, bottom row (idx 8..15) blue 0x0000FF
@ (both read as intended under either LED-buffer interp). Clearly distinct from the
@ stock red idle fill. Reversible; reflash stock to restore.
@ ============================================================================
custom_page_tick:
    push {r4, r5, lr}

    @ --- call the stock arp_3474 (r0=tick already set on entry) ---
    movw r4, #0x3475           @ arp_3474 @0x08013474 | thumb
    movt r4, #0x0801
    blx  r4

    @ --- gate: paint only when arp is OFF ---
    movw r4, #0x4AE1           @ arp_get_state @0x08014AE0 | thumb
    movt r4, #0x0801
    blx  r4
    cbnz r0, 1f                @ arp on -> yield to stock arp page

    @ --- paint our page (last write of the tick -> wins) ---
    movw r5, #0xBB51           @ led_set_color @0x0800BB50 | thumb
    movt r5, #0x0800
    movs r4, #0                @ pad index
2:                             @ top row 0..7 -> green
    mov  r0, r4
    movw r1, #0xFF00
    blx  r5
    adds r4, r4, #1
    cmp  r4, #8
    blo  2b
3:                             @ bottom row 8..15 -> blue
    mov  r0, r4
    movw r1, #0x00FF
    blx  r5
    adds r4, r4, #1
    cmp  r4, #16
    blo  3b
1:
    pop  {r4, r5, pc}
