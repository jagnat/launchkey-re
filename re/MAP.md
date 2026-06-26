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

## Vector table / ISRs (scripts/scan_vectors.py)
All exception + SVD-named IRQ handlers named in `symbols.tsv`. Cross-checks:
- **TIM1_UP_TIM10_IRQHandler == `led_key_matrix_scan_isr`@080095A8** (the matrix scan
  runs off TIM1) — independent confirmation of the LED/key engine.
- **TIM2_IRQHandler**@08008378 = a real ISR (candidate **arp/tempo clock** — check when
  chasing the arp engine).
- **OTG_FS_IRQHandler → `usb_otg_fs_isr`@08018184** (1298 B, 24 callees) — USB **is**
  interrupt-driven (earlier "polled" guess was wrong). USB device stack spans ~0x08015800
  -0x08019xxx (physically interleaved with the `confstore`/`extdata` .c ranges).
- Most other IRQ vectors point to weak default stubs in the `0x0801D2xx` cluster (unused
  peripherals).
- `assert_failed`@0800DC6C = the `__FILE__`/line assert sink.
Regenerate/extend with `scripts/scan_vectors.py`.

## USB-MIDI RX path (note 19) — the musical-engine gateway
Source modules (from kept `__FILE__` strings): `inputmidi_listener.c`@0x08011xxx,
`midiobj_backend.c`@0x08014xxx. USB ports: MIDI Port / DAW Port / "MIDI Int" (InControl).
| symbol | addr | role |
|---|---|---|
| `midi_in_router` | `0x0800C0C6` | ★ parse+dispatch incoming MIDI → 12 type handlers (17 callees) |
| `midi_in_publish` | `0x080116A4` | ★ fan-out event to listeners (all 12 handlers call it) |
| `midi_note_state_get`/`set` | `0x0800CDCC`/`0x0800CDF8` | ★ read/write MIDI note state (27 callers) |
| `g_midi_note_value_ptr` | `0x0801531C` | ★ 16ch×128×2B 14-bit value table (`&0x3fff`) |
| `g_midi_note_state_ptr` | `0x08015320` | ★ 16ch×128×1B note on/off+vel |
| `g_note_active_matrix_ptr` | `0x08016C00` | ☆ held-note set (arp input), engine 0x08016xxx |
| 12 handlers | `FUN_0801179c…0801215a` | ? one per message type (note-on/off/CC/pitchbend) — not yet split |
| `FUN_0800C238`/`C2D6` | — | ☆ the two input feeds (USB vs DAW) |
| MIDI-out builders (`…|0x90`) | `FUN_0801bbec`,`FUN_0801acf0`,`FUN_08017940` | ☆ engine emitting MIDI (capture target) |

## Config / storage stack (Tier-1 deep-dive)
External **SPI NOR flash** (opcodes confirm it) holds config/custom-modes. Layered:
| layer | symbol | role |
|---|---|---|
| SPI xfer | `spi1_xfer`@09502, `spi1_dma_driver`@0953E | SPI1 (+DMA) primitive |
| flash HW (`serstor_hw.c`) | `serstor_flash_write_enable`@09E2C (WREN 0x06), `_erase`@09E98 (0xD8/0x20), `_write`@09F0C (0x02 page-prog), `_read`@09F60 (0x03), `_run`@09FBA (status-poll 0x05 + multi-page), `serstor_get_handle`@0A156 | SPI NOR driver |
| region pumps | `confstore_flash_pump`@0D76A (erase 0x21000), `confsys_flash_pump`@15DAC, `extdata_flash_pump`@17F14 | per-region async op state machines (ctx[3]=cmd 2=erase/3=write/5=read) |
| config sys (`confsys*.c`) | `config_init`@0DCC0, `confsys_init`@15B94 (boot load+validate, dual-bank CRC), `confsys_load_validate`@0A5B0, `confsys_obj_xfer`@15FF4 (vtable obj read/write) | config system |
| external (`extdata_*.c`) | (mostly unnamed) | read/write config over SysEx/USB |
Note: `extdata_msd`=USB mass-storage (fw-update drive), `extdata_upn`=user-product-number
(focusrite register URL), `extdata_upgrade`=firmware upgrade. Big unnamed config funcs
left: 0x080170F8 (1032B), 0x0801989A, 0x0800EC54 (MSD parser).

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
