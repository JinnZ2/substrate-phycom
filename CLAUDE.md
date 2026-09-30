# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is
The connective layer above three repos: geometric-to-binary (encoder),
BE2-communication (transport), orbital-phycom (one expander). This repo
makes the EXPANDER pluggable and adds a terrestrial (geomagnetic/field)
expander so the architecture runs with no orbit.

## Core invariant
You transmit the SEED, not the message. A shared deterministic physics
model (the Expander) regenerates it. The model never crosses the wire —
it is both the compression and the gate.

Stated precisely, because the loose version was tested in round 2 and
does not survive as written (NOTEBOOK.md F-13). The reference fold is
SHA-256 truncated to 120 bits: one-way. `expand()` returns floats, and
nothing here inverts a hash. Two regimes actually move a message:

- **A — shared codebook.** The seed *selects* a message the far end
  already holds. Seed-only on the wire. **This is the regime that
  compresses**, and it requires an enumerable shared message space.
  **Pass `key=expander.model_key()` unless the codebook is secret** —
  unkeyed it has no gate at all (F-16).
- **B — physics-keyed pad.** The expander's keystream carries an
  arbitrary message. Wire carries seed + message-sized ciphertext, so
  this is secrecy, not compression.

Say which regime you mean.

## What the field model is worth (measured, F-17)
`expanders/geomagnetic.py` reads as though the field is the secret. It
is not. Declination/inclination/intensity are published geophysics and
are not independent — all three are functions of position, so the triple
is a 2-D manifold. Measured: 186 keys/km², ~2^21 against a county-level
guess, ~2^35 knowing nothing. **The field is a salt, not a key.** Real
strength must come from `anchor` / `lattice_hash` (surveyed data). Treat
a guessable anchor with an empty lattice_hash as UNKEYED. Re-run:
`python tools/measure_field_entropy.py`

## Layout
- core/seed.py      : the unit crossing every layer (120-bit + model_id + epoch + CRC16)
- core/expander.py  : abstract Expander. Same seed in, deterministic schedule out.
- expanders/orbital.py     : reference adapter to orbital-phycom (Kepler)
- expanders/geomagnetic.py : terrestrial field-model expander (the new piece)
- expanders/template.py    : copy this to add a carrier; states the four obligations
- integration/demo.py            : end-to-end, two carriers, the shared-model gate
- integration/demo_regenerate.py : regimes A and B (F-13)
- integration/demo_failures.py   : corrupt seed / wrong model_id / wrong params
- tests/test_stack.py  : determinism + round-trip + gate + the round-2 gaps
- tests/test_legacy.py : golden vectors + legacy ledger integrity
- legacy/          : retired modes, still executable. Precedent carries.
- NOTEBOOK.md      : the ledger — every claim, run, falsification, open unknown
- tools/           : check_stdlib_only.py enforces the no-deps rule

## House rules
- stdlib only. No deps. Must run on a phone. (Enforced: tools/check_stdlib_only.py)
- CC0. No extraction.
- Determinism is the contract. Same seed + same model + same epoch = identical output.
- New carrier? Copy expanders/template.py. seed.py and BE2 transports stay unchanged.
- **Anything that changes the output must change the model_id.** A peer
  who disagrees should be rejected, never silently divergent.
- **Retire, don't delete.** A superseded mode moves to legacy/modes.py with
  a RETIRED entry and a golden vector. It never just disappears — a seed
  minted under it still has to expand.
- Claims get run, not reasoned about. Record the result in NOTEBOOK.md
  even when it holds. Never edit a past round to match what you learned later.

## Design choices (constant pairs, default first)
| Where | Default | Retired |
|---|---|---|
| `seed_from_message(fold=)` | `FOLD_SAFE` | `FOLD_FLAT` |
| `FieldModel(key_version=)` | `KEY_V2` | `KEY_V1` |
| `lattice_hash_from_axes(version=)` | `LATTICE_V2` | `LATTICE_V1` |
| `OrbitalExpander(entropy=)` | `ENTROPY_FULL` | `ENTROPY_PARTIAL` |
| `OrbitalExpander(t_mode=)` | `T_ABSOLUTE` | `T_NORMALIZED` |
| `Expander.keystream(fold=)` | `KEYSTREAM_SIGNED` | `KEYSTREAM_ABS_MOD` |

Retired values are defined in `legacy/modes.py` and re-exported by the
module that honours them. `PYTHONPATH=. python -m legacy.modes` prints
why each was retired and which test killed it.

## What both endpoints must agree on out of band
Nothing in this list travels on the wire, and a mismatch in any of it
breaks expansion: the expander class, every model parameter (for
geomagnetic: `declination_deg`, `inclination_deg`, `intensity_nt`,
`anchor`, `lattice_hash`, `key_version`), the `fold` used to mint the
seed, the epoch time base, and — for regime A — the codebook.

`model_id` covers the mode flags only. Same `model_id` with different
`FieldModel` parameters passes every check and diverges silently; that
is the gate working, not a bug (`demo_failures.py`, case 3).

## Run
PYTHONPATH=. python -m integration.demo
PYTHONPATH=. python -m integration.demo_regenerate
PYTHONPATH=. python -m integration.demo_failures
PYTHONPATH=. python tests/test_stack.py
PYTHONPATH=. python tests/test_legacy.py
python tools/check_stdlib_only.py
python tools/measure_field_entropy.py

## Before adding features
Read NOTEBOOK.md's open unknowns and the potential-applications list —
measurement has already ruled two directions out, and knowing which is
cheaper than rediscovering them. Currently important: U-8 (`model_id` is
19 of the seed's 40 wire bytes, which is why it loses to the ecosystem's
existing 25-byte claim codec) and U-9 (the keyed fold has no strong
second factor until a real survey's entropy is measured).

<!-- clone-refspec-note v1.1 -->
## Cloning and pushing
Shallow clones are single-branch by default.
Before pushing any branch other than the default
branch, run:

    git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
    git fetch --depth 1

Or clone with: git clone --depth 1 --no-single-branch <url>
Without this, the first push of a new branch
fails the tracking-ref check even when the
commit landed.
<!-- /clone-refspec-note v1.1 -->
