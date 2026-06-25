# Hardware map — STM32F401 peripheral usage (Launchkey Mini MK3)

Built from `scripts/scan_mmio.py` (peripheral-base/register literals matched against
`tools/svd/STM32F401.svd`) cross-referenced with the corpus. Confidence: ★ verified by
register evidence, ☆ strong inference, ? guess. Function names with `~` were attributed
via a trailing literal pool (heuristic — exact attribution comes after the SVD-labeling
pass). Raw rows: `re/peripherals.tsv`.

## Peripheral inventory (what the MCU drives)
| peripheral | refs | role | evidence / driver fn |
|---|---|---|---|
| **TIM1** (0x40010000) | 4 | ★ matrix scan timebase + LED BCM/PWM | `SR`,`RCR`,base in `FUN_08009878`,`FUN_08009d94` |
| **GPIOA/B/C/D** (0x40020000+) | 13 | ★ LED+key/button matrix I/O | see matrix section |
| **ADC1** (0x40012000) | 4 | ☆ analog in = pitch/mod **touch strips** | `FUN_08009bee`,`FUN_0800d992` |
| **DMA1/DMA2** (0x40026x00) | 5 | ☆ DMA for SPI/ADC streaming | `FUN_0800953e` (with SPI1) |
| **SPI1** (0x40013000) | 3 | ? serial bus (LED shift regs? ext device?) | `FUN_0800953e` + DMA |
| **SPI2** (0x40003800) | 2 | ? | `FUN_08008e6c` (init) |
| **USART1/2/6** | 5 | ? UART(s) — DIN-MIDI? debug? inter-MCU? | `FUN_08009cb0` (USART6) |
| **I2C1** (0x40005400) | 2 | ? EEPROM (settings storage)? | `FUN_08008e6c` (init) |
| **OTG_FS** (0x50000000) | ~2 | ★ USB-MIDI (host link / DAW) | `FUN_080083bc`,`FUN_080100e6` |
| **RCC** (0x40023800) | 11 | ★ clock tree + per-periph enables | `SystemInit` + each MspInit |
| **FLASH** (0x40023C00) | 2 | ☆ flash latency / self-write (settings) | `FUN_08009398` |
| **PWR/SYSCFG/EXTI/IWDG/CRC** | 1 ea | ☆ std init: power, EXTI mux, watchdog, CRC | init paths |
| TIM2/3/4/5/9/10/11, TIM8 | 1–2 ea | ? aux timers (tempo/arp clock, debounce, PWM) | scattered |

Note: many regs are reached via a struct base in a register + immediate offset, so
counts undercount true usage. UART/SPI/I2C roles are unconfirmed — resolve by reading
their drivers after the SVD pass.

## The LED + key/button matrix (the part you asked about)
Strong register-level evidence for a **TIM1-clocked GPIO matrix**, consistent with
notes 09–10 (8×16 BCM LED matrix + key/button scan), now pinned to specific ports:

| direction | port/reg | addr | meaning | fn |
|---|---|---|---|---|
| **drive** | `GPIOB->BSRR` | 0x40020418 | ★ strobe matrix lines (set/reset) | `FUN_08009878`, `FUN_0800d992` |
| **drive** | `GPIOA->BSRR` | 0x40020018 | ★ strobe matrix lines | `FUN_0800d2e0` region |
| **read**  | `GPIOC->IDR`  | 0x40020810 | ★ **sense key/button columns** | `FUN_0800da4c` |
| **timebase** | `TIM1->SR`  | 0x40010010 | ★ scan/PWM interrupt flag | `FUN_08009878` |
| also | GPIOA/C base | — | row/column address + LED data | `FUN_08009878` |

So: **TIM1 fires → an ISR strobes a row via GPIOA/B BSRR → reads the column state via
GPIOC IDR → updates the LED bitplanes (BCM) and queues key/button events.** GPIOD is
also touched in init (extra rows/columns or LED enables).

Driver-function candidates (promote to `symbols.tsv` once confirmed by reading):
- `FUN_08009878` → ☆ `matrix_scan_step` (writes GPIO BSRR, reads TIM1 SR)
- `FUN_0800da4c` → ☆ `key_column_read` (reads GPIOC IDR)
- `FUN_08009d94` → ☆ `tim1_pwm_setup` (TIM1 base + RCR)
- `FUN_08008e6c` → ☆ `gpio_init_all` (loads every GPIO base; the MspInit/pin config)
- (cf. note 09's `led_key_matrix_scan_isr` @0x080095A8 — relate these; the BSRR/IDR
  work may live in helpers it calls.)

## Analog & comms (lower confidence, worth a look)
- **ADC1** → ☆ pitch/mod **touch strips** (the Mini MK3's two touch sliders). Confirm by
  reading `FUN_08009bee`/`FUN_0800d992` for channel config + where the result is sent
  as MIDI pitchbend/CC.
- **USB OTG_FS** → ★ the USB-MIDI endpoint (host/DAW). This is the **MIDI RX gateway**
  to the note/arp engine — high-priority follow-up.

## Next (to turn ☆/? into ★)
1. **SVD register-labeling pass** (`tools/svd/STM32F401.svd`) so `re/firmware.c` shows
   `GPIOC->IDR` etc. and `q.py xref` gives *exact* driver attribution (no `~`).
2. Read the candidate drivers above; promote confirmed names into `symbols.tsv`.
3. Follow `OTG_FS` → USB-MIDI RX → note dispatch (the musical-engine entry).
