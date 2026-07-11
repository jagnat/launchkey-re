# 37 — The clock/tempo engine: one counter to rule them all

*(2026-07-10, static RE session — M4 prep. Reference: `re/map/clock.md`.)*

## Why we went looking

Every M4 candidate (looper, note-bounce, generative) lives or dies on timing. Before
designing any of them we needed answers to: where do "ticks" come from, what units is
tempo stored in, and is there a song-position counter we can use? The map had exactly one
breadcrumb: `TIM2_IRQHandler` marked "candidate arp/tempo clock". This session pulled that
thread all the way through.

## The detective story, step by step

**1. Start at the interrupt.** `TIM2_IRQHandler` turned out to be tiny: check the update
flag, increment `*0x20002400`, increment the word after it. So TIM2 is just a metronome
for the CPU — but at what rate, and who listens?

**2. Identify the units by finding a delay loop.** One consumer (`delay_ticks_busy`) spins
until the counter advances N — a classic busy-wait `delay_ms`. Strong hint the counter is
1 kHz, confirmed later by the µs math (below).

**3. The `timer_elapsed` idiom unlocks everything.** The firmware never uses callbacks for
timing. Instead there's a 12-byte primitive: `timer_elapsed(latch, counter_ptr)` returns
`*counter_ptr - *latch` and re-latches. Every timed subsystem holds (a) a pointer to some
shared counter and (b) a private latch, and polls the difference each main-loop pass.
Once you recognize the shape, "who consumes this clock?" becomes a mechanical xref query.

**4. Find the 0xF8 sender.** We knew from live capture (note 21) that the device free-runs
MIDI clock at 120 BPM. Grepping the decompile for `0xf8` found exactly one
`midi_send(port, 0xf8, ...)` — inside a 46-byte pump that diffs a tick counter and emits
one clock byte per tick. Its struct told us the tick counter lives at `0x200014b8`.

**5. Walk into the owner struct.** That address had *no* direct xrefs — it's `+0x20`
inside a struct at `0x20001498`, reached via a base pointer. Grepping xrefs for the
`0x200014xx` region exposed a neat cluster of ~12 small accessors plus one 446-byte
main-loop function: the whole clock module, previously nameless.

**6. Read the engine.** `clock_engine_pump` runs every ms and adds 1000 to a phase
accumulator; when phase ≥ `period_us` it fires a tick. That's the entire internal clock:
**tempo is just "microseconds per 24 PPQN tick"**. The SysEx tempo handler nailed the
formula — it computes `2,500,000 / BPM` (and 60e6 µs/min ÷ 24 PPQN = 2.5e6, so the units
check out; 120 BPM → 20 833 µs/tick, matching the measured 48 ticks/s).

**7. The surprise: a dead transport.** The engine has full start/stop/continue/external-
sync machinery — an external-tick queue, a 4-window tempo estimator with confidence
gating, a separate "transport ticks" counter that only advances while "running". But the
start/stop/tick-RX entry points have **zero callers**, and their Thumb addresses appear
nowhere in flash as function pointers. It's shared-codebase inheritance (the SL/bigger
Launchkeys sync to external clock; the Mini doesn't wire it). Even the Play button only
*transmits* 0xFA/0xFC to the host — it never touches the engine.

## Why this is great news for M4

- **The looper's timebase already exists**: poll `g_clock_ticks` (24 PPQN) with the same
  latch+diff idiom stock code uses — no ISR hooking, no new timer.
- **The dead transport is free real estate.** `clock_transport_start/stop` and
  `g_clock_transport_ticks` are functional, tested-by-inheritance code that *nothing on
  this product uses*. A looper can own them outright as its play/stop + song position.
- **Tempo is one function call**, and there's even a stock SysEx command (`0x0A`, BPM
  20–600) we can drive from the host with zero firmware changes.
- Bonus understanding: LED "pulse" modes breathe in tempo because the LED compositor
  derives its phase from the same tick counter (mod 48 = 2 beats).

## Methodology takeaways (the teachable bits)

- **A measured fact makes static RE cheap.** Knowing (from MIDI capture) that the device
  free-runs 0xF8 at exactly 120 BPM turned "find the tempo engine" into "grep for 0xf8 and
  check the math".
- **Recognize the project's timing idiom first.** Once `timer_elapsed`+latch was
  understood, every consumer of every clock became enumerable. Frameworks repeat.
- **"Zero callers" + "address absent from flash" = dead code**, but on shared-codebase
  firmware it's often *intact* dead code — which for modders is inventory, not garbage.
  (Still needs one HW test before we rely on it — queued in validation.md.)
- Naming pass: 27 new symbols promoted to `re/symbols.tsv`, corpus regenerated (29.8%
  functions named, 38.4% of code bytes).

## What's still open

- HW validation trio (see validation.md backlog): external-sync deadness, SysEx tempo,
  transport-counter no-op claim. All black-box MIDI, zero flash risk — device just wasn't
  plugged in this session.
- `FUN_0801a4a4`: the *other* caller of `clock_set_tick_period_us` — probably a second
  SysEx/extdata tempo path, unread.
- The twin ms counter at `0x20002404` has no identified reader.
