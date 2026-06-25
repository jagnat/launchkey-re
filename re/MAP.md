# Firmware map — curated cheat-sheet (read this at session start)

Dense, high-confidence facts so we don't re-derive. Confidence: ★=verified,
☆=strong inference, ?=guess. Update when `symbols.tsv` grows.

## Memory
| region | addr | notes |
|---|---|---|
| App load base | `0x08008000` | ★ image = 88,088 B, ends ~`0x0801D818` |
| Flash data/const | ~`0x0801A000`+ | ★ palette, velocity curves, tables live here |
| SRAM | `0x20000000`–`0x2000FFFF` | ★ 64 KB; init SP `0x2000FFF8` |

## Named symbols (also in symbols.tsv)
| addr | name | conf | what |
|---|---|---|---|
| `0x080095A8` | `led_key_matrix_scan_isr` | ★ | TIM1-ISR 8×16 BCM matrix scan (notes 9–10) |
| `0x080141C2` | `led_render_resolve_palette` | ★ | descriptor idx → palette RGB → rgb buffer |
| `0x08012608` | `velocity_curve_apply` | ★ | installs curve `g_velocity_curves[idx]` (note 18) |
| `0x080126FC` | `velocity_curve_set` | ★ | clamp ≤3, store `g_settings+2`, re-apply, light LED |
| `0x0801267C` | `settings_apply_all` | ☆ | re-applies many `g_settings` fields on mode restore |
| `0x0801CF14` | `SystemInit` | ★ | RCC HSION etc. |
| `0x0801D1E4` | `app_start` | ★ | C runtime entry |
| `0x0801D250` | `Reset_Handler` | ★ | vector[1] |
| `0x0801C250` | `g_color_palette` | ★ | 128×4 B, **B,G,R,pad** (note 16) |
| `0x0801A158` | `g_velocity_curves` | ★ | 3 sets × 2 ch × 128 B, ends `0x0801A458` (note 18) |
| `0x080127F0` | `g_settings_subtable_127f0` | ☆ | 3×u16 `{0,0x5555,0xaaaa}`, indexed by `g_settings+4` |
| `0x20002128` | `g_settings` | ★ | RAM device-settings struct (see below) |
| `0x20003868` | `g_led_descriptors` | ★ | 16 B each; `+0x0f` = palette index (notes 12/16) |
| `0x2000AE40` | `g_led_rgb_buffer` | ★ | physical per-LED RGB the ISR shifts out |

**Hardware drivers (SVD-proven, see `hardware.md`):** `peripheral_init_all`@080083BC,
`timers_init_all`@08009D94, `systemclock_config`@0800DBD4, `key_columns_read`@0800D9D8
(GPIOC_IDR), `matrix_row_drive`@0800D8BC (GPIOB_BSRR), `matrix_pin_reconfig`@080093EA,
`key_event_scan`@08009878, `key_debounce`@0800DA4C, `adc_dma_driver`@0800D900 (touch
strips), `spi1_dma_driver`@0800953E. Registers labeled in `firmware.c` via `LoadSvd.java`
+ `ApplyMmioPointers.java`; query with `q.py reg <REG>`.

## `g_settings` @ 0x20002128 (the thread into musical features)
Pointer used in code as `DAT_080127d8`. Known fields (offset from base):
| off | meaning | conf |
|---|---|---|
| `+0` | velocity curve index, set A (0–2 curve, 3=fixed) | ☆ |
| `+2` | velocity curve index, set B — written by `velocity_curve_set` | ★ |
| `+1,+3,+4,+5,+6,+0x0e` | read by `settings_apply_all` → other mode toggles/selectors | ? |
| `+4` | indexes `g_settings_subtable_127f0` (<3) | ☆ |
→ **Next:** decode the remaining fields by reading each `settings_apply_all` callee.

## Pointers / leads to chase (still `FUN_`/`DAT_`)
| addr | role | conf |
|---|---|---|
| `0x0801B5B0` | caller of `velocity_curve_set` — likely SysEx/settings dispatcher | ☆ |
| `0x080126D0`,`0x080126EE`,`0x08012724`,`0x08012770`,`0x080127BC` | sibling `g_settings` handlers (found via `q.py xref 0x20002128`) | ☆ |
| `0x0800CEBC` | `led_desc_get_or_create` (used by velocity_curve_set) | ☆ |
| `0x0800F8E0` | installs a transform LUT (called by velocity_curve_apply) | ☆ |
| `DAT_0800CF98` | LED-descriptor manager: count `+0xc`, array ptr `_DAT_0800CF9C` | ☆ |

## Open TODO (offline)
- [ ] SVD-Loader pass (`tools/svd/STM32F401.svd`) → register names in decompile.
- [ ] HAL BinDiff vs compiled CMSIS/HAL → auto-name library leaves.
- [ ] Decode remaining `g_settings` fields → find arp/chord/scale config.
- [ ] Find USB-MIDI RX → note-dispatch (the musical-engine gateway).
- [ ] Locate scale/chord/arp interval tables (scan_tables.py had candidates near
      `0x0800DE..`, `0x08010700`).
