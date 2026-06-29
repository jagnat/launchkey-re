# Note 30 — Low-hanging-fruit bulk pass (thunks + nullsubs)

**Avenue:** coverage, but a different *shape* of coverage. The previous rounds (notes 26-29)
went deep on a few large, important functions — great for byte%, but function% lagged (lots of
big functions named, count still low). This round deliberately inverts that: hit **many tiny
functions** to pull the function-count percentage up toward the byte percentage.

## The idea: classify, don't read

993 of 1233 functions were still unnamed; ~400 of them are under 16 bytes. You can't *read*
400 functions cheaply, but you can **pattern-match their decompiled bodies** for two categories
that are identifiable without understanding their role:

- **Thunks** (`j_<callee>`): a body ≤24 B whose *only* function call is to an already-named
  function. That's a forwarder/veneer — honest to name `j_<callee>` (the standard "jumps to"
  convention). 29 found.
- **Nullsubs** (`nullsub_<addr>`): a body that is exactly `return;`. 45 found — but only after
  a crucial safety cap (below).

`scripts/classify_stubs.py` does this: splits `firmware.c` on the `==== name @ addr ====`
markers, pulls each unnamed function's body, counts calls, and emits proposals. `--apply`
merges them into `symbols.tsv` (sorted, skipping existing). Dry-run by default.

Result: **210 → 284 functions (17.0% → 23.0%)**, while byte coverage barely moved
(29.1% → 29.5%) — exactly the intended lift, since every one of these is tiny.

## The one trap that mattered: "return;" ≠ empty

My first cut treated *any* `return;`-only body as a nullsub and caught 85. That's wrong. Two
ways a non-empty function renders as bare `return;`:

1. **Register-arg loss.** Functions reached by tail-call keep their args in registers; the
   decompiler loses them and may render real work as `return;`. I'd already met two of these
   in note 29 (`FUN_08014ef4`/`f10`, the `ctrl_out_dispatch` iterators) — they do real work.
2. **Memory barriers / delays.** An 8-byte `dsb; isb; bx lr` (common in peripheral init)
   decompiles to bare `return;` because the barrier has no data effect Ghidra can show. I
   spot-checked the 8-byte "empty" functions called from `peripheral_init_all` — almost
   certainly barrier stubs, *not* no-ops. Naming them `nullsub` would assert "does nothing,"
   which is false (they enforce ordering).

The fix: **only ≤4 B counts as nullsub.** A 2-byte Thumb function can only be `bx lr` (empty)
or `b .` (trap) — and a trap renders as a `while(true)` loop, not `return;`. So ≤4 B + exactly
`return;` is provably empty. Quality over count: I left ~40 ambiguous "empty-looking" functions
unnamed rather than mislabel them.

## Why the tool is worth keeping

It's idempotent and gets *more* productive over time: every time a core function gets a real
name, the small forwarders that tail-call it become classifiable as `j_<that>`. So re-running
`classify_stubs.py --apply` after each future milestone is near-free coverage. The thunk
category is, in effect, a coverage multiplier on the deep work from notes 26-29.

## Bookkeeping

- +74 funcs (29 thunks, 45 nullsubs) → 284/1233 (23.0%), 29.5% bytes.
- New reusable tool `scripts/classify_stubs.py`; MAP coverage line + naming-convention note
  updated (`j_` and `nullsub_` prefixes explained).
- Session arc (notes 26-30): 180 → 284 functions (14.6% → 23.0%).
