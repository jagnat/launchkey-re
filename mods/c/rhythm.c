/* Euclid rhythm engine — C port of mods/asm/rhythm_decode.s (HW-validated
 * 2026-07-01; measured gap sets matched euclid_ref.py exactly). Detoured from
 * stock rhythm_decode @0x080175B0; stock rhythms 0-4 behave identically.
 *
 * Three control surfaces, in precedence order:
 *   1. UI override (UI->euclid_on): k/n/rot straight from the ui_state struct,
 *      set live by the Euclid app page (mods/c/ui.c). Canceled by a deliberate
 *      selector change from the stock arp page / DAW CC 0x5b, so the two
 *      surfaces never fight.
 *   2. Pad-row presets (selector 5..10, keeper mod): k = sel-1,
 *      n = 16 - (deviate >> 3) from the held-Arp Deviate knob.
 *   3. Stock rhythms 0-4 (O / OXO / OXXO / Random / Deviate).
 */

#include "ui.h"

uint32_t euclid_mask(uint32_t k, uint32_t n, uint32_t rot)
{
    if (n < 1) n = 1;
    if (n > 16) n = 16;
    if (k < 1) k = 1;
    if (k > n) k = n;
    uint32_t mask = 0;
    for (uint32_t i = 0; i < n; i++)
        if ((i * k) % n < k)                 /* Bjorklund: hit on slot 0 */
            mask |= 1u << ((i + rot) % n);
    return mask;
}

void rhythm_decode_new(volatile uint8_t *cfg, uint32_t reset)
{
    if (!cfg) {
        if (reset)
            RHY->step = 0;
        return;
    }
    uint32_t sel = cfg[3];
    if (RHY->last_sel != sel) {
        reset = 1;
        if (UI->magic == UI_MAGIC)
            UI->euclid_on = 0;               /* stock surface reclaims */
    }
    RHY->last_sel = sel;

    uint32_t mask = RHY->mask, period = RHY->period, flag = 0;

    if (UI->magic == UI_MAGIC && UI->euclid_on) {
        period = UI->n;
        if (period < 1)  period = 1;
        if (period > 16) period = 16;
        mask = euclid_mask(UI->k, period, UI->rot);
    } else if (sel == 0) { mask = 1; period = 1; }
    else if (sel == 1) { mask = 5; period = 3; }     /* OXO  */
    else if (sel == 2) { mask = 9; period = 4; }     /* OXXO */
    else if (sel == 3) { flag = 1; mask = 1; period = 1; }   /* random */
    else if (sel == 4) {                             /* deviate */
        uint32_t d = cfg[9];
        if (d) { mask = 0x80 - d; period = 8; }
        else   { mask = 1; period = 1; }
    } else if (sel <= 10) {                          /* pad-row presets */
        uint32_t n = 16 - (cfg[9] >> 3);
        mask = euclid_mask(sel - 1, n, 0);
        period = n;
    }                                                /* sel > 10: keep */

    RHY->random = (uint8_t)flag;
    RHY->mask = mask;
    RHY->period = period;
    if (reset)
        RHY->step = 0;
}
