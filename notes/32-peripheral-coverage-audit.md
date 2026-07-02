# Note 32 — Peripheral coverage audit ("anything unmapped HW-wise?")

**Question that drove this:** is any *peripheral* still unmapped? Different from "what % of
functions are named" — this asks specifically about the hardware drivers.

## How to audit peripheral coverage in this corpus

Registers aren't raw addresses in the decompile — the SVD pass (`LoadSvd.java` +
`ApplyMmioPointers.java`) labels each literal-pool pointer as `PTR_<REG>_<addr>` (e.g.
`PTR_GPIOC_IDR_0800db28`), and code dereferences through those. So `q.py reg` finds nothing;
the real query is **grep `PTR_<REG>` and map each to its containing function**, then check if
that function is named. `scripts/` gained a throwaway audit (kept in scratch) that buckets
`PTR_<REG>` by peripheral and lists named vs unnamed touchers.

That immediately showed which peripherals were genuinely *un*driven (no named function touching
them at all): **CRC, EXTI, FLASH, PWR, USART** — and, hiding in plain sight, **I2C** (only an
incidental `I2C1_CR1` poke from the LED ISR was named; the actual 328-byte transfer state
machine `FUN_0800d024` was not).

## What the gaps turned out to be

- **`usart_init`** (08009CB0): configures CR1/CR2/CR3 + baud for USART1/2/6. The Mini has no
  DIN MIDI, so these are debug/inter-MCU UARTs — but they're real and now named.
- **`crc_compute`** + **`crc_update_byte`** (0801895C/08018944): the CRC32 unit — enable clock,
  reset, feed words big-endian into `CRC_DR`, bitwise poly step for trailing bytes. This is the
  engine behind the dual-bank config CRC validation (`confsys_*`).
- **`exti_config`** (08009A7C): EXTI IMR/EMR mask + edge-mode setup.
- **`clock_config_boot`** (08008DC2): the low-level bringup — FLASH_ACR latency=2, PWR_CR
  voltage scaling, HSE on, PLL config, sysclk→PLL. (Distinct from the higher-level
  `systemclock_config`.) Closes both FLASH and PWR in one function.
- **`flash_cache_enable`** (08009398): FLASH_ACR I-cache + D-cache + prefetch.
- **`i2c_xfer`** / **`i2c1_init`** (0800D024/08008E6C): the real I2C driver + its pin/clock init.
- RCC helpers: `rcc_{ahb1,apb1,apb2}_enable` clock-gate shims, `rcc_pwr_clk_enable`, and the
  three clock-frequency getters `rcc_{hclk,pclk1,pclk2}_from` (read RCC_CFGR prescaler bits).
- `gpio_pin_config` (0800999C): the per-pin MODER/OTYPER config primitive (HAL_GPIO_Init-like).
- USB pin/PHY: `usb_gpio_init` / `usb_otg_gpio_init` (PA11/PA12 + OTG_FS).

## A Ghidra gotcha worth remembering: phantom "functions"

`ExportCorpus` lists `FUN_080127a6` as a function (it appears in `firmware.c` with a marker),
but `ImportSymbols` **silently can't rename it** — it isn't a real `Function` object in the
Ghidra DB (it's a thunk/veneer Ghidra tracks differently). Symptom: `ImportSymbols miss=0` yet
the named-function count comes up one short of the symbols.tsv row count, and
`classify_stubs.py` keeps re-proposing the same address every run (its `--apply` writes a row
that never takes effect, polluting the source of truth). Fix: a `PHANTOM` ignore-set in
`classify_stubs.py` (currently just `080127a6`). The GPIO veneers `FUN_08008d4e/d50` are the
same kind of phantom — left unnamed deliberately.

## Answer

**No whole peripheral is unmapped.** Every STM32F401 peripheral the firmware uses (RCC, GPIO
A-E, all the TIMs, SPI1/2, I2C1, USART1/2/6, ADC1, DMA1/2, USB OTG FS, CRC, EXTI, FLASH, PWR,
SYSCFG, IWDG, RTC) now has at least one named driver/handler. What remains in the MMIO sweep is
a handful of tiny redundant veneers and Ghidra phantoms — not drivers.

## Bookkeeping

- +20 funcs this sweep → 320/1233 (26.0%), 32.4% bytes.
- MAP "Hardware drivers" section expanded with a peripheral-driver table + the phantom caveat.
- `classify_stubs.py` hardened with a PHANTOM skip-set.
