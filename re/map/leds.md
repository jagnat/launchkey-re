# LEDs, pad pages, render architecture

Confidence: ★=verified, ☆=strong inference, ?=guess.

## LED hardware + palette basics
| addr | name | conf | what |
|---|---|---|---|
| `0x080095A8` | `led_key_matrix_scan_isr` | ★ | TIM1-ISR 8×16 BCM matrix scan (notes 9–10); TIM1_UP_TIM10_IRQHandler |
| `0x080141C2` | `led_render_resolve_palette` | ★ | descriptor idx → palette RGB → rgb buffer |
| `0x0801C250` | `g_color_palette` | ★ | 128×4 B, **B,G,R,pad** (note 16) |
| `0x20003868` | `g_led_descriptors` | ★ | 16 B each; `+0x0f` = palette index (notes 12/16) |
| `0x2000AE40` | `g_led_rgb_buffer` | ★ | physical per-LED RGB the ISR shifts out |
| `DAT_0800CF98` | LED-descriptor manager | ☆ | count `+0xc`, array ptr `_DAT_0800CF9C` |
| `0x0800CEBC` | `led_desc_get_or_create` | ☆ | used by velocity_curve_set |

## LED compositor — TWO LAYERS + attr select (why naive led_set_color fails)
- **palette layer** `DAT_0800bb98` (idx*4+8): written by `led_render_resolve_palette`@`0x080141C2`
  = `color = palette_tbl(DAT_080143f4)[descriptor[+0xf] & 0x7f]` → `FUN_0800bb36`. Idle pads =
  palette idx **42** (=0x2a) → our `led-palette-42-red` mod turns idle red.
- **direct layer** `DAT_0800bba8` (idx*4): written by `led_set_color`@`0x0800BB50`(idx<0x80, rgb).
- **attr byte** `DAT_0800bbac[idx]`: **bit7 `0x80` = DIRECT-select** (use direct layer), bits6-4
  mode, bits2-0 group. Set via `led_attr_set_direct`@`0x0800BB6C` (`FUN_0800bb6c`(idx,mode<3) →
  `&0xf | mode<<4 | 0x80`; mode≥3 CLEARS 0x80 → back to palette). The compositor
  (`FUN_0800ba5c`/`ba74` cluster → physical `g_led_rgb_buffer`@`0x2000AE40`) picks direct vs
  palette per pad by `0x80`. `led_render_resolve_palette` does NOT clear `0x80`.
- **To paint a pad and WIN:** `led_attr_set_direct(idx,mode)` **then** `led_set_color(idx,rgb)`
  — exactly what `led_pad_paint_direct`@`0x080125EE` (`FUN_080125ee` = `FUN_0800bb6c(idx,0)`+
  `led_set_color`) does for the arp page. `0x00FF00`=green, `0x0000FF`=blue in either interp.

## Pad-page render state machine (2026-07-01/02, HW-proven)
**No central "current page" switch — broadcast + self-gate.** Two SEPARATE broadcast systems +
the two-layer compositor above.

**(1) Input broadcast** — `control_dispatch`@`0x0800C72C` (invoked via callback ptr in
`main_task_tick`'s literal pool @`0x0800C99C`; pumped near `0x0800C70C`) calls every page input
handler in sequence (`arp_30ca`, `arp_3244`, `transport_button_handler`, `arp_control_handler`,
`FUN_08013cfc`, `FUN_08013f96`, …) with the control id in `param_1`. Gate `FUN_0800c616`
(=`*DAT_0800c644`) splits a normal path from a secondary `switch` (velocity-curve @`param_1`==1,
brightness @0x13, …). Known button ids (`param_1`): 0x17 Play, 0x19, 0x60/0x61 round btns, 0x62,
0x64/0x65 encoder. `DAT_0800c644`=1 set by `FUN_0800c5f6` (from `peripheral_init_all`); which page
= layer-1 **NOT pinned** (Shift renders layer-0, so ≠ Shift).

**(2) Per-tick engine chain** — `main_task_tick`@`0x0800C914` (from `peripheral_init_all` loop,
only when `FUN_0800c616()==0`): `FUN_08012ae0`,`FUN_08014ab4`,`arp_3164`,`FUN_08012c72`,
**[`nullsub_080081d4`]**,`FUN_08012ddc`,**[`nullsub_080081f4`]**,`FUN_08013dd8`,`nullsub_080127ec`,
`FUN_08014064`,`arp_3340`,`arp_3474`. This is the arp step-timer + a few EDGE-triggered renders
(`arp_3340`/`3474` fire only on arp-state change, touch btns 0x60/0x61). **Runs every frame at
standalone idle** → the right hook layer for a custom page.

**(3) The DAW/host pad-page renderer** — `pad_page_render_dispatch`@`0x0800BC2C` (callers
`FUN_080195bc`/`0801989a`/`0801b17e`). Walks a STACK of page-render callbacks (interleaved with
`FUN_0800bc78`=per-page arg-refresh): **[`nullsub_0801009a`]**, **[`nullsub_080101c2`]**,
`FUN_0801055c`, `FUN_0801092a`, `FUN_08010c72`, `FUN_08010dea` — the `0x08010xxx` cluster IS the
set of pad pages (idle/session, drum, DAW/InControl [route 6/id 0x78 special-cased at the tail]),
each self-gating on its active flag. Callbacks registered via `page_layer_push`@`0x0800CE9A`
(push fn-ptr onto manager `DAT_0800cf98`, count `+0x30`, MAX 8, array `+0x10`; callers = the
`0x08010xxx` pages + `settings_led_init` + layer-1 entry). Page activation marks the page-struct
descriptor `+0xf |= 1` (tail of dispatch). **⚠ Does NOT run at standalone idle** (verified on HW,
incl. with a DAW open) — see dead ends in MAP.md.

**Dispatch arg flow (asm-confirmed):** `pad_page_render_dispatch(r0,r1,r2)` saves args→`r4/r5/r6`;
`FUN_0800bc78`@`0x0800BC78` (empty in decompile — it's `mov r2,r6;mov r1,r5;mov r0,r4;bx lr`)
**re-supplies `(r0,r1,r2)` before EACH page renderer**. Caller `FUN_0801989a` invokes it as
`(r0=ctx/r8, r1=0, r2=&stackbuf)` @`0x08019924`. **A renderer in an empty slot MUST preserve
`r4/r5/r6`.** Empty-slot call-sites: `0x0800BC40` `bl nullsub_0801009a` (bytes `04f02bfa`),
`0x0800BC48` `bl nullsub_080101c2`.

**Pages = per-control ROUTING, not a page enum:** there is NO "current page" variable. Each
`0x08010xxx` page renderer is called per control being processed and CLAIMS it only if the
control's route matches its page — pattern (see `FUN_08010dea`, `FUN_0801055c`):
`if (ctrl_group(id) != G || route_channel_get(id) != C || id != SPECIFIC) return;` then mark
descriptor `+0xf |= 1` + render. Helpers: `ctrl_group`@`0x080111A6` (= `id>>4`),
`page_mode_context`@`0x080104B6` (mode 0x14/0x15/0x16/0x17/0x18/0x1a →
`DAT_080106d0 + 0x34/0x124/0x214/0x304/0x3f4/0x4e4`, 6×0xf0 sub-mode contexts; `0`=not owned).
A control's MODE nibble (`control_raw_read(id) & 0xf000`) = `0x2000` → InControl/DAW
(`route_is_incontrol`@`0x0800B8D2`), per-control, no global. Page init `FUN_08010458` builds a
page from a pad-LAYOUT STRING (`s_..._Q222222Q_777777_0801071c`, 6 regions × `FUN_0800ce3c`) +
`layout_observer_add`/`scale_observer_add`. "Switching pages" = routes get reconfigured (Arp btn
/ DAW handshake reroute controls). The **arp page is a SEPARATE subsystem** (`0x08013xxx`,
event-driven, direct-color) layered via the compositor.

## Custom-page recipe (RENDER SEAM PROVEN on HW 2026-07-02)
Hook **`main_task_tick`**'s empty slot: redirect call-site `bl nullsub_080081d4` @`0x0800C95A`
(thumb_bl detour, build.py `detour_call=True`). Per pad: `led_attr_set_direct(idx,0)` **then**
`led_set_color(idx,rgb)` — the direct bit is the one fix all early attempts lacked. Preserve
r4/r5/r6 (r4=tick, r5=state ptr reused after the slot). HW result: full 16-pad grid owned at
idle. Second empty slot available: `bl nullsub_080081f4`.
**Remaining problem = the page GATE + INPUT, not the seam** (see MAP.md Current status):
`arp_is_enabled()`@`0x080148B0` (byte@`0x2000e268`) flips with the arp engine → poor page
selector; arp-panel-active byte@`0x2000e628`+0. Scratch byte in use for diagnostics:
`0x2000DD37` (LED attr array tail, idx 0x7f — safe while pad 0x7f unused).

## Failure post-mortems (keep — they encode the model)
- **v1 `custom_page.s` / `custom-idle-page`** (attic): (a) gated on `arp_get_state()==0`, but
  that's a TRI-STATE (0/1/2: `(*p!=0)`, →2 if `*(p+4)!=0`) whose 0 = the held-Arp view → it
  overpainted the real arp page; use `arp_is_enabled()` for the true arp-on bool. (b) called
  `led_set_color` WITHOUT `led_attr_set_direct` → at idle pads stayed palette-mode (showed
  palette-42 red); on the arp page arp had already set `0x80` so the green stuck — misleading.
- **v2.1** hooked `pad_page_render_dispatch`'s empty slot @`0x0800BC40` → showed nothing at
  standalone idle (that dispatch is the DAW/host page path).
- **v2.2 `page_slot.s`** (superseded): seam correct, but gate `arp_is_enabled()==0` = green when
  arp off / red when latched on, and red in the settings/shift layer (`main_task_tick` skips its
  chain when `FUN_0800c616()!=0`) — gate unusable as a page selector.
