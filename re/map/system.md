# System: hardware drivers, ISRs, settings, config/storage, misc leads

Confidence: ★=verified, ☆=strong inference, ?=guess. See also `re/hardware.md` (board map)
and `re/peripherals.tsv`.

## Boot / runtime anchors
| addr | name | conf | what |
|---|---|---|---|
| `0x0801CF14` | `SystemInit` | ★ | RCC HSION etc. |
| `0x0801D1E4` | `app_start` | ★ | C runtime entry |
| `0x0801D250` | `Reset_Handler` | ★ | vector[1] |
| `0x080083BC` | `peripheral_init_all` | ★ | init + the main polled loop (runs `main_task_tick`, `control_surface_scan`, …) |

## Hardware drivers (SVD-proven)
`timers_init_all`@08009D94, `systemclock_config`@0800DBD4, `key_columns_read`@0800D9D8
(GPIOC_IDR), `matrix_row_drive`@0800D8BC (GPIOB_BSRR), `matrix_pin_reconfig`@080093EA,
`key_event_scan`@08009878, `key_debounce`@0800DA4C, `adc_dma_driver`@0800D900 (touch strips),
`spi1_dma_driver`@0800953E. Registers labeled in `firmware.c` via `LoadSvd.java` +
`ApplyMmioPointers.java` as `PTR_<REG>_<addr>` literals (grep those, not `q.py reg`).

**Peripheral coverage = complete (2026-06-28).** Audited via `PTR_<REG>` usage; every MMIO
peripheral the firmware uses has ≥1 named driver:
| peripheral | driver(s) | role |
|---|---|---|
| Clock/Flash/PWR | `clock_config_boot`@08008DC2, `flash_cache_enable`@08009398, `rcc_hclk_from`@0800DBF0, `rcc_pclk1_from`@0800DBFC, `rcc_pclk2_from`@0800DC0C | HSE+PLL+flash-latency+voltage-scale bringup; flash I/D-cache; HCLK/PCLK1/PCLK2 freq from RCC_CFGR prescalers |
| RCC enables | `rcc_ahb1_enable`@0800833C, `rcc_apb1_enable`@08008342, `rcc_apb2_enable`@0800835A, `rcc_ahb1_enable2`@080093C4, `rcc_pwr_clk_enable`@0800D870 | `RCC_xxxENR \|= mask` clock-gate shims |
| GPIO | `gpio_pin_config`@0800999C | per-pin MODER/OTYPER/etc config primitive (6 callers) |
| USART1/2/6 | `usart_init`@08009CB0 | configures CR1/CR2/CR3 + baud for the 3 UARTs (candidate debug-serial seam) |
| I2C1 | `i2c_xfer`@0800D024 (xfer state machine), `i2c1_init`@08008E6C (clocks+pins) | the real I2C driver |
| CRC | `crc_compute`@0801895C, `crc_update_byte`@08018944 | CRC32 unit (enable, feed words BE, bitwise byte step) |
| EXTI | `exti_config`@08009A7C | EXTI IMR/EMR mask + edge-mode config |
| USB GPIO | `usb_gpio_init`@0801586E, `usb_otg_gpio_init`@08015864 | PA11/PA12 + OTG_FS pin/PHY setup |
Remaining unnamed MMIO-touchers are tiny redundant veneers (GPIO config thunks
`FUN_08008d4e/d50` — Ghidra phantoms that won't take a name).

## Vector table / ISRs (scripts/scan_vectors.py)
All exception + SVD-named IRQ handlers named in `symbols.tsv`. Cross-checks:
- **TIM1_UP_TIM10_IRQHandler == `led_key_matrix_scan_isr`@080095A8** (matrix scan off TIM1).
- **TIM2_IRQHandler**@08008378 = a real ISR (candidate arp/tempo clock).
- **OTG_FS_IRQHandler → `usb_otg_fs_isr`@08018184** — USB is interrupt-driven (earlier
  "polled" guess was wrong).
- Most other IRQ vectors → weak default stubs in the `0x0801D2xx` cluster (unused peripherals).
- `assert_failed`@0800DC6C = the `__FILE__`/line assert sink.
Regenerate/extend with `scripts/scan_vectors.py`.

## `g_settings` @ 0x20002128 (thread into device settings)
Pointer used in code as `DAT_080127d8`. Known fields (offset from base):
| off | meaning | conf |
|---|---|---|
| `+0` | velocity curve index, set A (0–2 curve, 3=fixed) | ☆ |
| `+2` | velocity curve index, set B — written by `velocity_curve_set` | ★ |
| `+1,+3,+4,+5,+6,+0x0e` | read by `settings_apply_all` → other mode toggles/selectors | ? |
| `+4` | indexes `g_settings_subtable_127f0`@`0x080127F0` (3×u16 `{0,0x5555,0xaaaa}`) | ☆ |
→ Next: decode the remaining fields by reading each `settings_apply_all`@`0x0801267C` callee.

Velocity: `velocity_curve_apply`@`0x08012608` (installs `g_velocity_curves[idx]`),
`velocity_curve_set`@`0x080126FC` (clamp ≤3, store `g_settings+2`, re-apply, light LED),
`g_velocity_curves`@`0x0801A158` (3 sets × 2 ch × 128 B, ends `0x0801A458`) (note 18).

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
(focusrite register URL), `extdata_upgrade`=firmware upgrade. Big unnamed config funcs left:
0x080170F8 (1032B), 0x0801989A, 0x0800EC54 (MSD parser).

## Pointers / leads to chase (still `FUN_`/`DAT_`)
| addr | role | conf |
|---|---|---|
| `0x0801B5B0` | caller of `velocity_curve_set` — likely SysEx/settings dispatcher | ☆ |
| `0x080126D0`,`0x080126EE`,`0x08012724`,`0x08012770`,`0x080127BC` | sibling `g_settings` handlers (via `q.py xref 0x20002128`) | ☆ |
| `0x0800F8E0` | installs a transform LUT (called by velocity_curve_apply) | ☆ |
| `0x0800F_` feature module | 68 funcs, mostly unmapped; entry points = the `control_claim_*` predicates + `ctrl_feature_write` (input.md) | |

## Open TODO (offline)
- [ ] HAL BinDiff vs compiled CMSIS/HAL → auto-name library leaves.
- [ ] Decode remaining `g_settings` fields.
- [ ] Split the 12 MIDI type handlers (`FUN_0801179c…0801215a`).
- [ ] Locate remaining interval tables (scan_tables.py candidates near `0x0800DE..`,
      `0x08010700`).
