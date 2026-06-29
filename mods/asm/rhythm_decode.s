    .syntax unified
    .thumb
    .global rhythm_decode_new

@ ============================================================================
@ rhythm_decode_new  — drop-in reimplementation of stock FUN_080175b0
@ (reached via a b.w detour installed at 0x080175B0 by mods/build.py).
@
@ void rhythm_decode_new(int cfg /*r0*/, int reset /*r1*/)
@   cfg = arp config struct @ 0x20001FAC (cfg[3] = rhythm selector)
@   reset = force step-counter reset flag
@ Writes rhythm pattern state @ 0x20001FE8:
@   +0  random flag   +4 mask(u32)   +8 period   +0x10 step ctr   +0x14 last-cfg
@
@ Behaviour: cfg[3] 0..4 == stock (O/OXO/OXXO/Random/Deviate, byte-identical to
@ the original immediates). cfg[3] 5..10 == PARAMETRIC Euclidean: k = Mutate (cfg[6],
@ CC 0x5a), n = Deviate (cfg[9], CC 0x5d), rot = 0, mask computed LIVE by euclid_compute.
@ This is the knob-wiring flash-experiment: arp_cc_in_handler already stages Mutate/Deviate
@ into cfg[6]/cfg[9] before calling rhythm_decode, so twisting those knobs (or sending the
@ CCs from a host) re-derives the rhythm. euclid_compute is the reusable track primitive.
@ ============================================================================
rhythm_decode_new:
    push {r4, r5, r6, lr}
    movw r3, #0x1FE8
    movt r3, #0x2000           @ r3 = pattern state base
    cbnz r0, 1f
    cmp  r1, #0
    beq  9f                     @ cfg==0 && reset==0 -> return
    movs r0, #0
    b    8f                     @ cfg==0 && reset    -> reset step ctr
1:
    ldrb r4, [r0, #3]           @ r4 = rhythm selector
    ldr  r2, [r3, #20]
    cmp  r2, r4
    it   ne
    movne r1, #1               @ selector changed -> force reset
    movs r6, #0                @ flag default 0
    ldr  r2, [r3, #4]          @ default: keep current mask...
    ldr  r5, [r3, #8]          @ ...and period
    str  r4, [r3, #20]         @ store new selector
    cmp  r4, #5
    bcc  .Lstock               @ <5 -> stock rhythms
    cmp  r4, #10
    bhi  7f                    @ >10 -> keep current (safety)
    @ ---- Euclidean (parametric): k,n live from the arp knobs ----
    @ Mutate (cfg[6], written by arp_cc_in_handler CC 0x5a) -> k
    @ Deviate (cfg[9], CC 0x5d)                              -> n
    @ This is the knob-wiring flash-experiment: euclid_compute clamps the ranges.
    push {r1}                  @ preserve reset flag across the call
    ldrb r4, [r0, #6]          @ r4 = mutate raw (k source)
    ldrb r5, [r0, #9]          @ r5 = deviate raw (n source)
    lsrs r0, r4, #3            @ k  = mutate >> 3   (~8..16 after CC clamp)
    lsrs r5, r5, #3            @     deviate >> 3   (0..15)
    adds r5, r5, #1            @ n  = (deviate>>3)+1 (1..16)   [r5 survives the call]
    mov  r1, r5                @ euclid_compute arg: n
    movs r2, #0                @ rot = 0
    bl   euclid_compute        @ r0 = mask  (clamps 1<=k<=n; preserves r3..r7)
    mov  r2, r0                @ mask -> store reg
    movs r6, #0                @ flag 0
    pop  {r1}                  @ restore reset flag
    b    7f                    @ period = n is already in r5
.Lstock:
    cmp  r4, #0
    bne  2f
    movs r2, #1
    movs r5, #1                @ 0: O
    b    7f
2:  cmp  r4, #1
    bne  3f
    movs r2, #5
    movs r5, #3                @ 1: OXO
    b    7f
3:  cmp  r4, #2
    bne  4f
    movs r2, #9
    movs r5, #4                @ 2: OXXO
    b    7f
4:  cmp  r4, #3
    bne  5f
    movs r6, #1                @ 3: Random (flag set)
    movs r2, #1
    movs r5, #1
    b    7f
5:  cmp  r4, #4
    bne  7f                    @ default -> keep current
    ldrb r2, [r0, #9]          @ 4: Deviate
    cbz  r2, .Ldev0
    rsb  r2, r2, #128          @ mask = 0x80 - cfg[9]
    movs r5, #8
    b    7f
.Ldev0:
    movs r2, #1
    movs r5, #1
7:
    strb r6, [r3, #0]          @ flag
    str  r2, [r3, #4]          @ mask
    str  r5, [r3, #8]          @ period
    cbz  r1, 9f
    movs r0, #0
8:
    str  r0, [r3, #16]         @ reset step ctr
9:
    pop  {r4, r5, r6, pc}

@ ============================================================================
@ euclid_compute  — THE reusable generator primitive (Time/Pitch/Octave tracks).
@   uint32 euclid_compute(uint k /*r0*/, uint n /*r1*/, uint rot /*r2*/)
@   returns n-bit mask in r0: k events distributed evenly across n slots (Bjorklund,
@   hit on slot 0), pattern rotated by rot. Clamps 1<=k<=n, n>=1.
@ Matches mods/euclid_ref.py exactly. Preserves r3-r7 (callee-saved here on purpose so
@ rhythm_decode_new keeps its state pointer in r3).
@ ============================================================================
    .thumb_func
euclid_compute:
    push {r3, r4, r5, r6, r7, lr}
    cmp  r1, #1
    it   lt
    movlt r1, #1               @ n = max(n,1)
    cmp  r0, #1
    it   lt
    movlt r0, #1               @ k = max(k,1)
    cmp  r0, r1
    it   gt
    movgt r0, r1               @ k = min(k,n)
    mov  r4, r0                @ r4 = k
    mov  r5, r1                @ r5 = n
    mov  r6, r2                @ r6 = rot
    movs r7, #0                @ r7 = mask
    movs r3, #0                @ r3 = i
.Lec_loop:
    mul  r0, r3, r4            @ r0 = i*k
    udiv r1, r0, r5            @ r1 = (i*k)/n
    mls  r0, r1, r5, r0        @ r0 = (i*k) mod n
    cmp  r0, r4
    bge  .Lec_next             @ skip if (i*k mod n) >= k
    add  r0, r3, r6            @ bitpos = (i+rot) mod n
    udiv r1, r0, r5
    mls  r0, r1, r5, r0
    movs r1, #1
    lsl  r1, r1, r0
    orrs r7, r7, r1            @ mask |= 1<<bitpos
.Lec_next:
    adds r3, r3, #1
    cmp  r3, r5
    blt  .Lec_loop
    mov  r0, r7                @ return mask
    pop  {r3, r4, r5, r6, r7, pc}
