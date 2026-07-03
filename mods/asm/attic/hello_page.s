    .syntax unified
    .thumb
    .global hello_page_render

@ ============================================================================
@ hello_page_render — "hello world" custom-page RENDER tracer.
@
@ Proves the pad-render extension SEAM: main_task_tick broadcasts each tick to a
@ chain of per-page render fns, INCLUDING an empty hook stub nullsub_080081d4.
@ We don't overwrite that 2-byte stub (too small, tightly packed); instead we
@ redirect its call-site `bl 0x80081d4` @0x0800C95A to here (build.py, kind=append
@ detour_call=True — emits a BL so lr is set and we return into main_task_tick).
@
@ On entry (reached by BL from 0x0800C95A):
@   r0 = tick delta (from the preceding `mov r0,r4`)   — we ignore it
@   lr = 0x0800C95E (return into main_task_tick)
@ Constraints: main_task_tick reuses r4 (tick) and r5 (state ptr) after us, so we
@ MUST preserve them. led_set_color is AAPCS (preserves r4-r11), so holding its
@ address in r4 across calls is safe once we've saved the caller's r4.
@
@ Effect: paints pads 0x0/0x5/0xa/0xf GREEN every tick, unconditionally. At idle
@ no other render owns those pads (the late renders early-return), so they light
@ and stay lit — visible proof the hook runs and we can drive the LED buffer.
@ 0x00FF00 = green under either buffer interp (RGB word or B,G,R bytes: mid=green).
@ Throwaway tracer — remove from build.py MODS after HW validation (→ v2 adds the
@ input-toggle + page flag for a real gated custom page).
@ ============================================================================
hello_page_render:
    push {r4, lr}
    movw r4, #0xBB51            @ led_set_color @0x0800BB50 | thumb bit
    movt r4, #0x0800

    movs r0, #0x0              @ pad 0
    movw r1, #0xFF00           @ green
    blx  r4

    movs r0, #0x5              @ pad 5
    movw r1, #0xFF00
    blx  r4

    movs r0, #0xa              @ pad 10
    movw r1, #0xFF00
    blx  r4

    movs r0, #0xf              @ pad 15
    movw r1, #0xFF00
    blx  r4

    pop  {r4, pc}
