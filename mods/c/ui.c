/* Custom UI layer — M1 (mode + home page) + M2.1 (surface capture) +
 * M3 (Euclid app).
 *
 * Compiled freestanding into the flash tail; the stock ROM is the OS.
 * ALL state lives in the scratch struct @0x2000F000 (build_block rejects
 * .data/.bss). Struct layout: mods/c/ui.h (offsets shared with ui_glue.s).
 *
 * Entry points (wired by the ui-layer mod's detours, see mods/build.py):
 *   ui_frame()          main_task_tick empty slot @0x0800C95A — every frame,
 *                       standalone layer-0 only (skipped in the shift layer).
 *   ui_on_press(id,v)   from ui_tap_emit (control_value_emit prologue).
 *                       Returns the swallow verdict: while the layer is
 *                       active, surface ids <0x80 never reach the stock
 *                       subscriber fan-out (keys >=0x80 always play).
 *   ui_on_release(id)   from ui_tap_release (control_value_release prologue).
 *   ui_dispatch_gate    (asm) aborts control_dispatch's layer-0 chain while
 *                       mode != 0.
 *
 * Control ids (★★ HW-measured, re/map/input.md): pads 0x00-0x0F reading
 * order, Fixed Chord 0x16, Shift 0x19, knobs 0x38-0x3F l-r. Knob values are
 * 16-bit (control_press_scan analog path scales to 0..0xFFFF).
 *
 * Map: Shift+pad8 toggles the layer from anywhere. Home (mode 1): pad0 =
 * Euclid app, pad8 = exit. Euclid app (mode 2): 16-pad live pattern view
 * (amber hit / dim rest / dark past-length, playing step white), knobs
 * 1/2/3 = k/n/rot, Fixed Chord = back to home.
 */

#include "ui.h"

/* ROM entry points (thumb bit set). Paint recipe per re/map/leds.md:
 * led_attr_set_direct(idx, mode<3) selects the direct layer (else palette),
 * THEN led_set_color(idx, 0xRRGGBB). */
static void (*const led_attr)(uint32_t idx, uint32_t mode)  = (void *)0x0800BB6D;
static void (*const led_color)(uint32_t idx, uint32_t rgb)  = (void *)0x0800BB51;

#define PAD_GATE   0x08   /* bottom-left pad: entry chord + home exit tile */
#define PAD_EUCLID 0x00   /* home: Euclid app tile */
#define ID_FIXED   0x16   /* Fixed Chord: in-app "back to home" */
#define ID_SHIFT   0x19
#define KNOB(i)    (0x38 + (i))

#define C_EXIT    0x400000  /* dim red */
#define C_EUCLID  0x605010  /* amber   */
#define C_HIT     0xC05000  /* pattern hit */
#define C_REST    0x100804  /* pattern rest */
#define C_STEP    0xFFFFFF  /* playing step (on a hit) */
#define C_STEP_R  0x303030  /* playing step (on a rest) */

static void pad(uint32_t i, uint32_t rgb) { led_attr(i, 0); led_color(i, rgb); }

static void restore_stock_leds(void)
{
    for (uint32_t i = 0; i < 16; i++)
        led_attr(i, 3);              /* mode>=3 clears the direct bit -> palette */
}

static void render_home(void)
{
    uint32_t t = (UI->frame >> 4) & 0x3F;       /* breathing violet */
    if (t > 0x1F) t = 0x3F - t;
    uint32_t bg = ((0x08 + t) << 16) | (0x10 + (t << 1));
    for (uint32_t i = 0; i < 16; i++)
        pad(i, bg);
    pad(PAD_EUCLID, C_EUCLID);
    pad(PAD_GATE, C_EXIT);
}

static void render_euclid(void)
{
    uint32_t mask = RHY->mask, period = RHY->period, step = RHY->step;
    if (period > 16) period = 16;
    for (uint32_t i = 0; i < 16; i++) {
        uint32_t c;
        uint32_t hit = (mask >> i) & 1;
        if (i >= period)      c = 0x000000;
        else if (i == step)   c = hit ? C_STEP : C_STEP_R;
        else                  c = hit ? C_HIT : C_REST;
        pad(i, c);
    }
}

void ui_frame(void)
{
    if (UI->magic != UI_MAGIC) {                /* first frame after boot */
        UI->magic = UI_MAGIC;
        UI->mode = 0;
        UI->shift_down = 0;
        UI->frame = 0;
        UI->euclid_on = 0;
        UI->k = 4; UI->n = 16; UI->rot = 0;
        return;
    }
    UI->frame++;
    if (UI->mode == 1)
        render_home();
    else if (UI->mode == 2)
        render_euclid();
}

/* Swallow verdict for ui_tap_emit: nonzero = skip control_value_emit's whole
 * subscriber fan-out. Active layer (before OR after handling, so entry/exit
 * presses are covered) owns every surface control (id < 0x80); keys pass.
 * Releases are never swallowed (stock press/release pairing can't wedge). */
uint32_t ui_on_press(uint32_t id, uint32_t value)
{
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
    } else if (UI->mode == 1) {
        if (id == PAD_GATE) {                   /* exit tile */
            UI->mode = 0;
            restore_stock_leds();
        } else if (id == PAD_EUCLID) {          /* enter Euclid app */
            UI->mode = 2;
            UI->euclid_on = 1;
            rhythm_decode_new(ARP_CFG, 0);
        }
    } else if (UI->mode == 2) {
        if (id == ID_FIXED) {                   /* back to home */
            UI->mode = 1;
        } else if (id >= KNOB(0) && id <= KNOB(2)) {
            uint32_t v = value >> 12;           /* 16-bit -> 0..15 */
            if (id == KNOB(0))      UI->k   = v + 1;   /* 1..16 */
            else if (id == KNOB(1)) UI->n   = v + 1;   /* 1..16 */
            else                    UI->rot = v;       /* 0..15 */
            rhythm_decode_new(ARP_CFG, 0);
        }
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
