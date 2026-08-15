# NOTEBOOK

The ledger for this repo. What was claimed, what was run, what fell
over, and what is still unknown.

This exists because the interesting part of a result is rarely the
result. It is the claim it killed. Code keeps the winner and throws away
the reasoning; six months later nobody remembers why the length prefix
is there, someone "simplifies" it out, and the same bug arrives wearing
a new name. So the reasoning is written down here and the losers are
kept in [`legacy/`](legacy/).

---

## The method

1. **State the claim so it can be killed.** "The fold is unambiguous" is
   a hypothesis. "The fold is good" is not — nothing can falsify it.
2. **Run it.** Not read it. A claim that has only been reasoned about
   has not been tested, and this repo has now been wrong twice about
   code that looked obviously correct.
3. **Record the result, including when it holds.** A claim that survived
   a real run is evidence, and it is worth as much as a falsification —
   it tells the next person where not to spend their time. Findings 7,
   10 and 12 held. They are written up at the same length as the ones
   that failed.
4. **If falsified: edit the claim, do not delete the evidence.** The old
   behaviour moves to `legacy/`, keeps working, and gets a golden vector
   pinning its exact output. The claim gets narrowed to whatever
   survived the run.
5. **Name the unknowns the run opened.** Every answer exposes a question
   that was invisible before it. Those go in [Open unknowns](#open-unknowns)
   with a status, not into someone's head.
6. **Rerun everything.** Not the one test you just wrote. The failure
   modes worth catching are the ones you did not predict, and the whole
   suite is 71 tests and under a second.

**The rule that makes the rest work:** never edit a past round to match
what you later learned. `legacy/reviews/02-code-audit.md` still contains
its original wrong guesses. Round 2 corrects them *below*, next to the
claim, where the correction is legible as a correction. An audit trail
that has been tidied up is not an audit trail.

### Entry format

```
F-nn  one-line claim
  Claim        what was believed, stated so it can fail
  Run          the command or test that actually exercised it
  Result       FALSIFIED / HELD / PARTIAL — and the observation
  Edit         what the claim became
  Opened       unknowns this run exposed
```

---

## Round 0 — construction

The stack was assembled from three existing repos: `geometric-to-binary`
(encoder), `BE2-communication` (transport), `orbital-phycom` (one
expander). This repo's contribution was to make the *expander* pluggable
and add a terrestrial one, so the architecture runs with no orbit.

No claims were tested in round 0. Everything below is the cost of that.

---

## Round 1 — audit

Twelve findings. Nine falsified something, three held. All twelve tests
are still in `tests/test_stack.py`; `tests/test_legacy.py` fails if any
of them is deleted while its `legacy/modes.py` entry still cites it.

### F-01 — epoch is 16 bits everywhere

- **Claim** epoch could be any int; the wire packs what it is given.
- **Run** pack an epoch above 0xFFFF and compare to what comes back.
- **Result** FALSIFIED. `to_wire()` silently truncated to 16 bits while
  the expander hashed the full value, so sender and receiver derived
  different keystreams from the "same" seed. Determinism broken by an
  input nobody thought was out of range.
- **Edit** epoch ∈ [0, 0xFFFF] enforced in `Seed.__post_init__`, so wire
  and expander cannot disagree. Rejected at construction, not at send.
- **Opened** [U-2](#u-2) — a 16-bit epoch is a small nonce space.

### F-02 — the message fold is unambiguous

- **Claim** `message + model_id + epoch` is a safe hash input, because
  model_id is a fixed known string like `"orbital.kepler.v1"` and no
  real message will land on that boundary.
- **Run** `test_fold_flat_ambiguous_pair_collision`.
- **Result** FALSIFIED. `(b"ab", "c")` and `(b"a", "bc")` fold to the
  same payload. The "fixed known string" premise was doing all the work
  and was never stated as a requirement anywhere a caller would see it.
- **Edit** `FOLD_SAFE` length-prefixes the message and is the default.
  `FOLD_FLAT` retired to `legacy/modes.py`.
- **Opened** nothing new — but see F-03, which is the same bug in
  another file, found separately because nobody went looking after the
  first one.

### F-03 — a FieldModel key is unique per place

- **Claim** `anchor + lattice_hash` identifies a location.
- **Run** `test_key_v1_collision`.
- **Result** FALSIFIED, and worse than F-02: `lattice_hash` defaults to
  `""`, so `("abc", "")` and `("ab", "c")` collide using nothing but
  ordinary anchor names. Two different places silently sharing a channel
  is the exact failure this layer exists to prevent.
- **Edit** `KEY_V2` length-prefixes the anchor and is the default.
  `KEY_V1` retired.

### F-03b — the lattice hash captures the geometry

- **Claim** hashing axis components in order captures a measured axis set.
- **Run** `test_lattice_hash_v1_loses_structure`.
- **Result** FALSIFIED. `[[a, b]]` and `[[a], [b]]` hash identically —
  vector count and arity are lost, so a 3×3 axis set is indistinguishable
  from a 9×1 one.
- **Edit** `version=LATTICE_V2` length-prefixes each vector; default.
- **Opened** the same mistake three times in one codebase. Written into
  `expanders/template.py` as an explicit warning, and asserted by
  `test_template_model_key_is_unambiguous`, so the file people copy
  cannot carry it forward.

### F-04 — `steps` sets resolution

- **Claim** `t = (k + epoch) / steps` is a time axis, so asking for more
  steps samples the same schedule more finely.
- **Run** `test_t_normalized_shape_changes_with_steps`.
- **Result** FALSIFIED. `expand(seed, 10)[:3] != expand(seed, 3)`.
  `steps` rescales the axis, so it changes the schedule's *shape*. Two
  peers who agreed on everything except buffer size got different
  schedules — a determinism break with no bad input anywhere.
- **Edit** `T_ABSOLUTE` divides by a fixed `sample_rate` instead.
  `T_NORMALIZED` retired. It remained the *default* through round 1 for
  backward compatibility; round 2 flipped the default, since `model_id`
  encodes the mode and a mismatched peer is therefore rejected rather
  than silently divergent.

### F-05 — the expansion uses the whole seed

- **Claim** one payload byte per channel spreads 120 bits of seed across
  the expansion.
- **Run** `test_entropy_partial_ignores_most_bytes`.
- **Result** FALSIFIED. With the default three periods, only
  `payload[0:3]` is ever read. Twelve of fifteen bytes are silent and
  the effective key space is 24 bits, not 120 — brute-forceable on a
  laptop while the docs advertised 120.
- **Edit** `ENTROPY_FULL` folds the whole payload into every channel via
  SHA-256. Default. `ENTROPY_PARTIAL` retired.

### F-06 — epoch advances time

- **Claim** raising the epoch steps the schedule forward.
- **Run** inspect `_t` under `T_NORMALIZED` with a large epoch.
- **Result** FALSIFIED under `T_NORMALIZED` — epoch slides the window
  without bound rather than advancing it on a grid, so "one epoch later"
  means a different amount of time depending on `steps`. Same root cause
  as F-04.
- **Edit** fixed by the same change. `T_ABSOLUTE` advances on a fixed
  grid: epoch=256 is exactly one `sample_rate` period past epoch=0.

### F-07 — the schedule covers [-1, 1] symmetrically

- **Claim** `(word / 32767.5) - 1.0` maps a 16-bit word onto [-1, 1].
- **Run** all 65536 words, round 2.
- **Result** **HELD.** Range is exactly [-1.0, 1.0]; `65535 / 32767.5`
  is exactly 2.0 in IEEE 754. No word maps to exactly 0.0, which is a
  curiosity, not a defect. Do not "fix" this divisor — 32768.0 would
  make the range asymmetric.

### F-08 — negative epoch is handled

- **Claim** negative epochs are rejected.
- **Run** construct a Seed with epoch=-1.
- **Result** FALSIFIED (inconsistently, which is worse than uniformly
  wrong): `to_wire()` silently wrapped it, `seed_from_message` rejected
  it. Two code paths, two behaviours, one type of input.
- **Edit** rejected once, at construction, with the range in the message.

### F-09 — bad wire input fails cleanly

- **Claim** short input is rejected.
- **Run** `test_from_wire_too_short_raises_value_error`.
- **Result** FALSIFIED on the *kind* of failure: it raised `struct.error`
  from inside the unpack, leaking an implementation detail that callers
  could not reasonably catch.
- **Edit** length checked before any unpacking; raises `ValueError` with
  the required minimum.
- **Round 2 note** extended to every single-bit flip and every truncation
  point — `test_single_bit_flip_rejected_everywhere_in_the_packet`,
  `test_truncated_wire_rejected`.

### F-10 — `expand(seed, 0)` is a live hazard

- **Claim** `steps=0` could reach a division and blow up.
- **Run** `expand(seed, 0)` on every expander, round 2.
- **Result** **HELD as safe.** `max(1, n_bytes)` in `keystream()` means
  zero is never passed from that path, and every expander returns `[]`
  from `range(0)` anyway. No defect. Now pinned by
  `test_steps_zero_returns_empty` so it stays true.

### F-11 — the keystream fold is fair

- **Claim** `int(abs(v) * 1e6) & 0xFF` fairly folds a schedule point.
- **Run** `test_keystream_signed_distinct_from_abs_mod` plus a byte
  distribution check.
- **Result** PARTIAL. `abs()` maps `v` and `-v` to the same byte, so one
  bit per sample is discarded by construction. But the output byte
  *distribution* is not measurably biased — the `1e6` scale scrambles
  it. So: a real information loss, not an exploitable one. Worth fixing,
  not worth panicking about. The distinction is the finding.
- **Edit** `KEYSTREAM_SIGNED` maps [-1, 1] to [0, 255] preserving sign;
  default. `KEYSTREAM_ABS_MOD` retired.

### F-12 — `t` never reaches 1.0

- **Claim** this is an off-by-one; no finite `steps` covers a full period.
- **Run** trace the half-open interval.
- **Result** **HELD as correct.** This is the standard half-open DFT
  convention: sampling `[0, 1)` is right, and "fixing" it to include the
  endpoint would double-count the period boundary. Documented in
  `expanders/orbital.py` so it does not get re-reported every audit.

### Round 1 consistency pass

Four inconsistencies were closed after the findings above, because the
fixes created them: modes changed behaviour without changing identity.

- **1.1** `seed_from_message` packed epoch as 4 bytes while the wire used
  2 — fixed to `!H` (F-01).
- **1.3** `OrbitalExpander.model_id` did not encode `entropy`/`t_mode`,
  so two peers in different modes agreed on the id and diverged in
  silence. Now `orbital.kepler.v1.e{full,part}.t{abs,norm}`.
- **1.4** same for `GeomagneticExpander` and `key_version`. Now
  `geomag.field.v1.kv{1,2}`.

The general rule that came out of it, now the first obligation in
`expanders/template.py`: **anything that changes the output must change
the `model_id`.** A silent divergence is far more expensive than a
rejected connection.

---

## Round 2 — this round

Round 1 fixed the code and left three things undone: the central claim
was never tested, the retired modes were scattered across the files that
superseded them, and none of the reasoning above existed outside commit
messages.

### F-13 — a shared physics model regenerates the message

This is the repo's headline invariant, and it had never been run.

- **Claim** (`CLAUDE.md`, `README.md`) "You transmit the SEED, not the
  message. A shared deterministic physics model regenerates the message."
- **Run** fold a message to a seed, expand it, try to get the message
  back. `integration/demo_regenerate.py`,
  `test_expansion_is_not_invertible_to_the_message`.
- **Result** **FALSIFIED as literally written.** `seed_from_message` is
  SHA-256 truncated to 120 bits — one-way by construction. `expand()`
  returns floats. No shared model inverts a hash, and none of the three
  expanders even claims to try. `integration/demo.py` never noticed
  because it stops at printing the schedule and never asks for the
  message back.
- **Edit** the claim splits in two, and the two halves trade off:

  | | Regime A: shared codebook | Regime B: physics-keyed pad |
  |---|---|---|
  | on the wire | seed only (15 B payload) | seed + message-sized ciphertext |
  | message space | must be shared and enumerable | arbitrary |
  | compresses? | **yes** — 40 B carried a 46 B message | no |
  | secrecy from | not holding the codebook | not holding the model |
  | recovery cost | one fold per candidate | one XOR |

  Both are implemented and tested. **Only regime A is compression**, and
  it buys that by requiring the message to already exist at the far end
  — which is not cheating, it is what a signal flag is, but it is not
  what the sentence promised. **Regime B is encryption**, and the seed
  is the key, not the message.

  The honest version of the invariant: *the shared model is the gate in
  both regimes, and the compression claim holds only where the message
  space is shared.* README and CLAUDE.md now say this.
- **Opened** [U-1](#u-1), [U-2](#u-2), [U-6](#u-6).

### F-14 — the docstrings' arithmetic

Round 1 left several numeric assertions in comments, unverified.

- **Run** round 2, directly.
- **Result** **ALL HELD.** CRC-16/CCITT-FALSE gives 0x29B1 for
  `b"123456789"` as claimed, so a seed validated here validates against
  BE2's spec. `65535 / 32767.5 == 2.0` exactly. No word maps to 0.0.
  `Expander()` is genuinely uninstantiable, as is a subclass that omits
  `expand()`. Nothing to fix; four fewer things for the next round to
  re-derive.

### Structural changes

- **`legacy/`** — retired modes moved to a single definition site, with
  `RETIRED` recording claim, killer test and replacement for each. The
  modules that still honour them import from there, so `grep -rn
  "legacy.modes" .` is the complete legacy surface.
- **Golden vectors** — `tests/test_legacy.py` pins the exact output of
  every retired mode *and* every current default. Today's default is
  tomorrow's legacy; pinning on the way in means the next round inherits
  evidence instead of reconstructing it.
- **Ledger integrity is tested** — a `RETIRED` entry citing a test that
  no longer exists fails CI. The ledger cannot rot quietly.
- **`T_ABSOLUTE` is now the default.** It was the only falsified mode
  still shipping as a default. `model_id` carries the mode, so an old
  peer is rejected rather than silently divergent, and old seeds still
  expand under an explicitly-configured legacy expander.
- **`expand_strict()` + `ModelMismatch`** — the round-1 review asked for
  a loud failure on unsupported `model_id`. `expand()` stays permissive
  because the gate demos need to show what a mismatch sounds like; the
  strict variant is the one to use at a real boundary.
- **`tools/check_stdlib_only.py`** — "stdlib only" was a hard constraint
  that nothing enforced. Now CI-enforced by AST parse, on 3.9/3.11/3.13.

---

## Round 3 — the two blocking unknowns, run

Round 2 closed with U-1 marked `BLOCKING` ("lives in another repo, not
runnable here") and U-6 marked `IMPORTANT` ("nobody has measured it").
Both are now run. Both changed the design.

### F-15 — is the real encoder invertible? (U-1)

- **Claim** `seed_from_message` is only a *reference* fold; the real one
  is `geometric-to-binary`, and if it is invertible then regime A stops
  needing a codebook and the compression claim gets much stronger.
- **Run** cloned `JinnZ2/geometric-to-binary` and read it.
- **Result** **The premise was wrong.** `geometric-to-binary` is not a
  message encoder at all — it is a SymPy physics playground: 90
  equations, a 112-edge morphism graph, numpy/sympy dependencies. There
  is no message-to-seed fold in it to be invertible.

  What it *does* carry is `CLAIM_SCHEMA.py`, a stdlib-only binary codec:

  ```
  encode_claim(dict) -> 25 bytes
  decode_claim(blob, table, id_lookup) -> dict     # needs CLAIM_TABLE.json
  ```

  So the stack's real encoder **is invertible — but only against a
  shared table.** That table is a codebook. Which means:
- **Edit** *Regime A is not a workaround for a missing inverse. Regime A
  is the architecture, and it always was.* The ecosystem already
  standardised on shared-table decoding before this repo existed; round
  2 rediscovered it from first principles and mistook it for a
  limitation.
- **Also run** all 90 real claims through a substrate-phycom round trip:

  | | bytes on the wire |
  |---|---|
  | prose | ~2400 B |
  | `.claims` pipe line | 137 B (mean of the 90) |
  | `encode_claim()` binary | **25 B** + 8,199 B shared table |
  | substrate-phycom seed | **40 B** + shared `.claims` + field model |

  90/90 recovered exactly, zero payload collisions, 0.1 ms mean search
  against the 90-entry codebook. It works — **and it loses.** The
  existing 25-byte codec already beats our 40-byte seed, so on this
  message space the seed buys no compression at all. 19 of those 40
  bytes are the `model_id` string. See [U-8](#u-8).
- **Opened** [U-8](#u-8), and it retires the framing of U-1 entirely.

### F-16 — regime A's gate (does not exist)

Found while running F-15, not looked for.

- **Claim** (round 2, the regime A table) regime A is "gated by not
  holding the codebook".
- **Run** `test_unkeyed_fold_gives_regime_a_no_gate`, and directly
  against the real corpus: attacker holds the public `.claims` file and
  no field model at all.
- **Result** **FALSIFIED, and it is a real hole.** `seed_from_message`
  hashes `(message, model_id, epoch)` — nothing else. `model_id` and
  `epoch` both travel in the clear on the wire. So anyone holding the
  codebook re-folds every entry and reads the message, and **the field
  model is never consulted by the fold at any point.** The attacker in
  the test recovers the plaintext claim immediately.

  Round 2 wrote "the codebook, not the seed, is the secret here" and
  did not follow the sentence to its conclusion: the codebooks in this
  ecosystem are CC0, in public repos. A public codebook is not a secret,
  so regime A as shipped had no gate whatsoever.
- **Edit** `seed_from_message(key=...)` — HMAC instead of bare SHA-256
  when a key is supplied, `b""` (default) reproducing every payload ever
  minted, so all golden vectors survive untouched. `Expander.model_key()`
  supplies it. Recovery now needs the codebook **and** the model.

  `model_key()` returns `b""` on the base class, and `OrbitalExpander`
  does not override it. That is deliberate: orbital's parameters are
  public or encoded in `model_id`, so it has no secret to offer, and
  claiming one it does not have would be worse than admitting it.
- **Opened** [U-9](#u-9).

### F-17 — how much key material is in a field survey? (U-6)

- **Claim** (round 2's estimate) an attacker knowing the region to ±1°
  and ±100 nT searches ~2000 × 2000 × 1000 ≈ 2^32 candidates.
- **Run** `python tools/measure_field_entropy.py` — centred tilted
  dipole, stdlib only, grid halved until the key count converges.
- **Result** **FALSIFIED — my own estimate was far too generous**, and
  wrong in method, not just in magnitude. It multiplied the three
  parameter ranges as though declination, inclination and intensity were
  independent. They are not: all three are functions of position, so the
  triple lies on a **2-dimensional manifold** in 3-space. Multiplying
  three ranges counts a 3-D box drawn around a 2-D surface. Measured
  overcount from that error alone: **107× at 10 km**, growing with area.

  Measured, at the rounding `FieldModel.key()` actually uses:

  | | |
  |---|---|
  | key density | **186 distinct keys per km²** (one per ~73 m square) |
  | attacker knows your county (100 km) | 2^21 — **372 ms** to exhaust |
  | attacker knows your region (1000 km) | 2^27.5 — 37 s |
  | attacker knows *nothing* about location | 2^35 — **0.06 core-days** |

  For comparison: the seed payload is 2^120 and HMAC-SHA256 is 2^256.
- **Edit** the module's story is inverted. It is written as though the
  field is the secret; the arithmetic says **the field is a salt and the
  anchor is the key.** A salt is not worthless — it makes the search
  per-place, so one broken channel does not break the next town over.
  But a `FieldModel` with a guessable `anchor` and an empty
  `lattice_hash` (the default) must be treated as **unkeyed**.
  `geomagnetic.py`, `expander.model_key()` and the README now say so.
- **Limits, stated** the dipole model omits crustal anomalies, which
  raise the local count. That does not rescue the claim — it relocates
  it. Anomaly structure is *surveyed* data, not published geophysics,
  which is exactly what `lattice_hash_from_axes` exists to fold in. The
  finding is not "the field is useless", it is "the *published* field is
  not the secret; the *survey* is."
- **Opened** [U-9](#u-9), [U-10](#u-10).

### What closed, what opened

| | |
|---|---|
| closed | U-1 (premise wrong; regime A is the architecture) · U-6 (measured: salt, not key) |
| opened | [U-8](#u-8) model_id dominates the wire · [U-9](#u-9) where does real key material come from · [U-10](#u-10) secular variation |

---

## Potential applications

Posed after round 3, and split honestly by what has actually been run.
The measurements above kill some obvious-sounding ideas, which is the
point of having run them first.

### Tested

**A1 — claim broadcast across the JinnZ2 ecosystem.** `.claims` corpora
are already shared, enumerable and stdlib-decodable — a ready-made
regime A codebook. All 90 claims round-trip, 0.1 ms recovery, zero
collisions. **But** the honest result is that the existing 25-byte
`encode_claim()` already beats a 40-byte seed, so *this is not a
compression win.* What it does buy, keyed, is a gate the plain codec has
no notion of: `encode_claim` output is readable by anyone with the
public table, a keyed seed is not. Use it where you want a claim
reference that only a co-located holder can resolve — not to save bytes.
Fix [U-8](#u-8) and the seed drops to ~21 B and wins on both.

**A2 — physics-keyed pad for arbitrary text** (regime B). Round-trips
any message, gated by the model. Real constraint: it does not compress,
and reusing `(seed, epoch)` reuses the pad. See [U-2](#u-2).

**A3 — two-factor place-bound reference** (F-16's keyed fold). Resolving
a seed requires the codebook *and* a survey of the place. Per F-17 the
published-field component is only ~2^21, so this is meaningful only
with a real `lattice_hash` — but the *structure* is sound and tested.

### Posed, not run

**A4 — emergency / off-grid codebook radio.** The natural home for
regime A: a fixed set of status messages and a grid-square location
codebook, seeds over CB/HAM/LoRa. Message spaces of tens to hundreds of
entries are where regime A is strongest and where a 15-byte payload
genuinely beats sending text. Needs [U-8](#u-8) to be worth the wire.

**A5 — quantized sensor telemetry.** Readings bucketed into a shared
quantization codebook; the seed selects a bucket. Same shape as A4,
with the codebook generated rather than written. Untested: whether
bucket counts stay small enough for the O(n) search.

**A6 — location-attested messaging.** Because the key is per-place, a
seed that resolves proves the sender held *that* place's survey. F-17
says the published field cannot carry this (2^21 is not an attestation),
but a private anomaly survey folded through `lattice_hash_from_axes`
might. **This is the most interesting untested direction, and it is
entirely contingent on [U-9](#u-9).**

**A7 — token-minimal agent corpora.** `CLAIM_SCHEMA.py`'s stated purpose
is cheap reading by AI agents. Seeds as claim references is a natural
extension — but the 8 KB shared table dominates until corpora are far
larger than 90 entries, so this earns nothing yet. Revisit at ~10k
claims.

### Ruled out by measurement

**Not a general-purpose compressor.** F-13 and F-15 together: the fold
is one-way, so the only compressing regime needs a shared enumerable
message space, and on the one real corpus available the existing codec
is already smaller. Seeds compress *selection*, not *content*.

**Not a cryptosystem keyed by geophysics.** F-17. Published field values
are a salt worth ~2^21–2^35. Anything that needs real key strength must
get it from surveyed data or conventional key material, and should say
which.

---

## Open unknowns

The live list. An unknown leaves this section by being **run**, not by
being reasoned about. Closed entries stay, with what closed them —
knowing a question is settled is worth as much as the answer.

<a id="u-1"></a>
### U-1 — is the real encoder invertible? `CLOSED, round 3 (F-15)`

~~`seed_from_message` is a reference fold. The real one is
`geometric-to-binary`. If that encoder is invertible, regime A stops
needing a codebook.~~

**The premise was wrong.** `geometric-to-binary` is a SymPy physics
playground, not a message encoder. The stack's actual encoder is
`CLAIM_SCHEMA.py`: invertible, but only against a shared
`CLAIM_TABLE.json`. That is a codebook. Regime A is not a workaround for
a missing inverse — it is the architecture the ecosystem already ran on.

<a id="u-2"></a>
### U-2 — nonce discipline is documented, not enforced `OPEN`

Regime B derives a keystream from `(seed, epoch)`. Reuse the pair, reuse
the pad — the classic break, and two messages under one pad is enough.
`epoch` is 16 bits (F-01), so a channel wraps after 65536 messages under
one model. Nothing in the code prevents any of this; `pad_apply`'s
docstring warns and that is all. **Run to close:** decide whether the
API should refuse a repeated `(model, seed, epoch)`, and whether 16 bits
is the right width now that it is load-bearing for secrecy rather than
just for replay-distinctness.

<a id="u-3"></a>
### U-3 — cross-machine bit-identity is asserted, never measured `OPEN`

`CLAUDE.md` says "identical output, on any machine". For the geomagnetic
and template expanders that is safe: HMAC-SHA256 plus integer division
is exact. `OrbitalExpander` calls `math.sin`, which comes from the
platform libm and is **not** guaranteed bit-identical across
platforms — the last ulp can differ. Golden vectors compare at 9 decimal
places for exactly this reason. **Run to close:** compare orbital golden
vectors across CI's three Pythons on Linux and at least one macOS/ARM
runner. If they differ, the fix is a fixed-point sine table, not a
loosened claim.

<a id="u-4"></a>
### U-4 — the wire leaks which physics you are running `OPEN`

`model_id` and `epoch` travel in the clear, so an observer learns the
carrier, the mode flags, and a replay counter without holding anything.
The message stays gated, but "there is a geomagnetic channel here, on
kv2, at epoch 42" is metadata, and the threat model this repo implies —
observers who should not know a channel exists — cares about metadata.
**Run to close:** write the threat model down, then decide whether
`model_id` should be a truncated keyed hash of the model rather than a
readable string.

<a id="u-5"></a>
### U-5 — 120-bit payload collision behaviour `OPEN`

Birthday bound puts a collision around 2^60 folds. Irrelevant for a
codebook of a few hundred entries; not obviously irrelevant for a
long-lived channel folding open-ended messages, especially since a
collision in regime A means the far end recovers *the wrong message*
with no error. **Run to close:** bound the realistic message volume per
model, then decide if 120 bits is the right size or just the size
`orbital-phycom` happened to use.

<a id="u-6"></a>
### U-6 — how much key material is really in a field survey? `CLOSED, round 3 (F-17)`

~~An attacker who knows the region to ±1° and ±100 nT searches roughly
2000 × 2000 × 1000 ≈ 2^32 candidates.~~

**Measured, and my estimate was wrong in method.** It multiplied three
parameter ranges as though they were independent; they are all functions
of position, so the triple is a 2-D manifold in 3-space (107× overcount
at 10 km, worse with area). Real numbers: **186 keys/km²**, 2^21 against
a county-level guess (372 ms), 2^35 knowing nothing at all (0.06
core-days). The field is a **salt**, not a key. Re-run any time with
`python tools/measure_field_entropy.py`.

<a id="u-7"></a>
### U-7 — regime A's search cost is unbounded in the docs `OPEN, MINOR`

`codebook_recover` is O(n) folds with no cap. Round 3 measured the
constant — 0.1 ms against a 90-entry codebook, so ~1.1 µs per fold — but
the cap is still missing, and it is a denial-of-service knob for an
attacker who can make a receiver search a large space against an
unmatchable seed. **Run to close:** decide a maximum codebook size or
take a cap parameter.

<a id="u-8"></a>
### U-8 — `model_id` is half the wire `OPEN, IMPORTANT`

Measured in F-15: a geomagnetic seed is 40 bytes on the wire, of which
**19 are the `model_id` string** and 15 are the payload. That is why the
seed lost to `encode_claim()`'s 25 bytes on the one real corpus we have.

Replacing the readable string with a 2-byte registry index would put the
seed at ~21 B — under the 25 B codec, turning A1 and A4 from "works but
loses" into a genuine win. It would also close most of [U-4](#u-4): a
2-byte index leaks far less than `"geomag.field.v1.kv2"`, and a
*truncated keyed hash* of the model would leak nothing to an observer
without the model.

The cost is a registry both ends must share — one more thing in the
out-of-band agreement, and a versioning problem when it changes.
**Run to close:** prototype the index, measure the wire, and decide
whether the registry belongs in this repo or in BE2.

<a id="u-9"></a>
### U-9 — where does real key material come from? `OPEN, IMPORTANT`

F-17 established that published field values are a salt (~2^21–2^35).
F-16's keyed fold is only as strong as what `model_key()` returns, so
right now the two-factor gate has one strong factor (the codebook, if
private) and one weak one.

`lattice_hash_from_axes` is the intended answer: a surveyed local
anomaly map, or a measured crystal axis set, is genuinely private data
rather than published geophysics. Nobody has measured how much entropy a
realistic survey carries, or how repeatably two parties can measure the
same object to 6 decimal places and derive the same hash — and if they
cannot, determinism breaks and the channel simply fails.

**This gates [A6](#potential-applications) entirely, and A6 is the most
interesting untested direction.** Run to close: take a real axis
measurement twice with the same instrument, see whether the hashes match
at the current rounding, then estimate the entropy of the measurement.

<a id="u-10"></a>
### U-10 — secular variation as a dimension `OPEN, MINOR`

The field drifts. `tools/measure_field_entropy.py` ignores this, which
makes its estimate *conservative* in one direction: an attacker must
also match the survey epoch, adding a dimension. It also means a survey
goes stale, and two parties who surveyed years apart derive different
keys and silently fail to communicate — the F-04 failure shape again,
in the physical layer. **Run to close:** bound the drift rate against
the rounding in `key()`, which gives both the added search cost and the
survey's shelf life.

---

## Running a round

For whoever picks this up next — including a future me who has forgotten
all of it.

```bash
PYTHONPATH=. python tests/test_stack.py      # the contract
PYTHONPATH=. python tests/test_legacy.py     # golden vectors + ledger
python tools/check_stdlib_only.py            # the house rule
PYTHONPATH=. python -m integration.demo             # happy path
PYTHONPATH=. python -m integration.demo_regenerate  # F-13, both regimes
PYTHONPATH=. python -m integration.demo_failures    # the three failure shapes
PYTHONPATH=. python -m legacy.modes                 # why each mode was retired
```

Then:

1. Pick an unknown from the list above. Prefer one marked `IMPORTANT` —
   currently U-8 (the seed loses on the wire until `model_id` shrinks)
   and U-9 (the keyed fold has no strong second factor until we know
   what a real survey is worth). U-9 gates A6, the most interesting
   untested application.

   Round 3's lesson on picking: U-1 was marked `BLOCKING` for a whole
   round on the assumption it was unrunnable. It took one `git clone`,
   and the answer was that the question's premise was wrong. Check
   whether an unknown is actually blocked before believing it is.
2. Restate it as something that can fail, and write the test *first*.
   If you cannot write a test that would fail, the claim is not yet a
   claim.
3. Run it. Record the result here even — especially — if it held.
4. If it falsified something: retire the old mode to `legacy/modes.py`
   with its `RETIRED` entry, add a golden vector, add the new default,
   and change the `model_id` if behaviour changed.
5. Add whatever unknowns the run opened. There are always some.
6. Rerun everything above, then append the round. Do not edit the ones
   already here.
