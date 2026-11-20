/* Shared state + ROM addresses for the custom UI layer (ui.c, rhythm.c).
 * The ui_state struct lives in scratch RAM @0x2000F000 (never zeroed at boot
 * -> magic-guarded init in ui_frame). Offsets are hardcoded in ui_glue.s
 * (+0 magic, +4 mode) — keep in sync. */
#pragma once
#include <stdint.h>

#define UI_MAGIC 0x55AC0DE5u

struct ui_state {
    uint32_t magic;        /* +0                                   */
    uint8_t  mode;         /* +4  0=stock, 1=home, 2=euclid app    */
    uint8_t  shift_down;   /* +5                                   */
    uint8_t  _pad[2];
    uint32_t frame;        /* +8                                   */
    uint8_t  euclid_on;    /* +12 rhythm-engine override live      */
    uint8_t  k, n, rot;    /* +13/+14/+15 euclid params (UI-owned) */
    uint8_t  arp_down;     /* +16 Arp button physically held       */
    uint8_t  pads_ceded;   /* +17 direct bits cleared for stock arp panel */
    uint8_t  arp_auto;     /* +18 we auto-enabled the arp at app entry    */
};
#define UI ((volatile struct ui_state *)0x2000F000)

/* Stock rhythm pattern state @0x20001FE8 (re/map/arp.md). random is written
 * as a byte by both stock and us; mask/period/step/last_sel are words. */
struct rhythm_state {
    uint8_t  random;       /* +0x00 */
    uint8_t  _pad[3];
    uint32_t mask;         /* +0x04 */
    uint32_t period;       /* +0x08 */
    uint32_t lfsr;         /* +0x0c (stock random-mode state, untouched) */
    uint32_t step;         /* +0x10 wraps at period */
    uint32_t last_sel;     /* +0x14 */
};
#define RHY ((volatile struct rhythm_state *)0x20001FE8)

#define ARP_CFG ((volatile uint8_t *)0x20001FAC)   /* +3 rhythm sel, +9 deviate */

/* rhythm.c */
void rhythm_decode_new(volatile uint8_t *cfg, uint32_t reset);
uint32_t euclid_mask(uint32_t k, uint32_t n, uint32_t rot);
