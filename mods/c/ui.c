/* Custom UI layer — M1 (mode + home page) + M2 (stock-UI input takeover).
 *
 * Compiled freestanding into the flash tail; the stock ROM is the OS.
 * ALL state lives in the scratch struct @0x2000F000 (build_block rejects
 * .data/.bss — nothing would initialize them). Struct offsets are shared
 * with mods/asm/ui_glue.s — keep the two in sync.
 *
 * Entry points (wired by the ui-layer mod's detours, see mods/build.py):
 *   ui_frame()          main_task_tick empty slot @0x0800C95A — every frame,
 *                       standalone layer-0 only (skipped in the shift layer).
 *   ui_on_press(id,v)   from ui_tap_emit    (control_value_emit prologue)
 *   ui_on_release(id)   from ui_tap_release (control_value_release prologue)
 *   ui_dispatch_gate    (asm only) aborts control_dispatch's layer-0 handler
 *                       chain while mode != 0 — stock UI is deaf in our modes.
 *
 * Control ids (★★ HW-measured, re/map/input.md): pads 0x00-0x0F in reading
 * order, Shift 0x19. Gate gesture: Shift + pad 8 (bottom-left) toggles.
 */

#include <stdint.h>

#define UI_MAGIC 0x55AC0DE5u

struct ui_state {          /* ui_glue.s offsets:      */
    uint32_t magic;        /* +0                      */
    uint8_t  mode;         /* +4  0=stock, 1=home     */
    uint8_t  shift_down;   /* +5                      */
    uint8_t  _pad[2];
    uint32_t frame;        /* +8                      */
};
#define UI ((volatile struct ui_state *)0x2000F000)

/* ROM entry points (thumb bit set). Paint recipe per re/map/leds.md:
 * led_attr_set_direct(idx, mode<3) selects the direct layer (else palette),
 * THEN led_set_color(idx, 0xRRGGBB). */
static void (*const led_attr)(uint32_t idx, uint32_t mode)  = (void *)0x0800BB6D;
static void (*const led_color)(uint32_t idx, uint32_t rgb)  = (void *)0x0800BB51;

#define PAD_GATE  0x08   /* bottom-left pad: entry chord + exit tile */
#define ID_SHIFT  0x19

#define C_EXIT    0x400000  /* dim red: back to stock */
#define C_EUCLID  0x605010  /* amber: future Euclid app tile (M3) */

static void pad(uint32_t i, uint32_t rgb) { led_attr(i, 0); led_color(i, rgb); }

static void restore_stock_leds(void)
{
    for (uint32_t i = 0; i < 16; i++)
        led_attr(i, 3);              /* mode>=3 clears the direct bit -> palette */
}

static void render_home(void)
{
    /* breathing violet background; triangle wave off the frame counter */
    uint32_t t = (UI->frame >> 4) & 0x3F;
    if (t > 0x1F) t = 0x3F - t;                 /* 0..31..0 */
    uint32_t bg = ((0x08 + t) << 16) | (0x10 + (t << 1));   /* R breathes, B floor */
    for (uint32_t i = 0; i < 16; i++)
        pad(i, bg);
    pad(0, C_EUCLID);
    pad(PAD_GATE, C_EXIT);
}

void ui_frame(void)
{
    if (UI->magic != UI_MAGIC) {                /* first frame after boot */
        UI->magic = UI_MAGIC;
        UI->mode = 0;
        UI->shift_down = 0;
        UI->frame = 0;
        return;
    }
    UI->frame++;
    if (UI->mode == 1)
        render_home();
}

/* Returns the SWALLOW verdict for ui_tap_emit: nonzero = do not run
 * control_value_emit's subscriber fan-out for this event. While the layer is
 * active (before OR after handling, so entry/exit presses are swallowed too),
 * all surface controls (id < 0x80: pads, buttons, strips, knobs) are ours
 * alone — no stock MIDI/LED/transport subscriber hears them. Keys (>= 0x80)
 * always pass so the keyboard keeps playing. Releases are never swallowed
 * (ui_tap_release passes through) so stock press/release pairing can't wedge
 * for presses stock saw before we went active. */
uint32_t ui_on_press(uint32_t id, uint32_t value)
{
    (void)value;
    if (UI->magic != UI_MAGIC)
        return 0;
    uint32_t was_active = UI->mode;

    if (id == ID_SHIFT) {
        UI->shift_down = 1;
    } else if (id == PAD_GATE && UI->shift_down) {  /* Shift+pad8: toggle */
        if (UI->mode == 0) {
            UI->mode = 1;                       /* paints on shift release */
        } else {
            UI->mode = 0;
            restore_stock_leds();
        }
    } else if (UI->mode == 1 && id == PAD_GATE) {   /* bare exit tile */
        UI->mode = 0;
        restore_stock_leds();
    }

    return (id < 0x80 && (was_active || UI->mode)) ? 1 : 0;
}

void ui_on_release(uint32_t id)
{
    if (UI->magic != UI_MAGIC)
        return;
    if (id == ID_SHIFT)
        UI->shift_down = 0;
}
