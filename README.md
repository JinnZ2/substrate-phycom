# substrate-phycom

[![License: CC0-1.0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![stdlib only](https://img.shields.io/badge/deps-none-brightgreen.svg)](tools/check_stdlib_only.py)
[![python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**Communication where the compression *is* the security boundary.**

You transmit a 15-byte seed. A shared, deterministic physics model —
which never crosses the wire — expands it. Someone holding the model
gets a schedule, a keystream, or a message. Someone without it gets
noise, and cannot tell the difference between "wrong model" and "close".

The connective layer above three repos:
[geometric-to-binary](https://github.com/JinnZ2/geometric-to-binary) (encoder),
[BE2-communication](https://github.com/JinnZ2/BE2-communication) (transport),
[orbital-phycom](https://github.com/JinnZ2/orbital-phycom) (one expander).
Its job is to make the **expander** pluggable, and to add a terrestrial
one — so the architecture runs with **no orbit**.

## Why this matters

Orbital-phycom needed a satellite. This doesn't. The terrestrial
expander uses the local geomagnetic field as the shared model: two
parties who know the field geometry of a place share a reference frame
that never travels over the air. Send the seed by CB, HAM, LoRa, or a
knock on a pipe — the ground you are standing on does the decompression.

That is the tribal navigation insight stated as engineering, and it
means the satellite stops being a dependency. It becomes, at most, one
optional anchor that sharpens the model.

## Run it

No install. No dependencies. Python 3.9+.

```bash
git clone https://github.com/JinnZ2/substrate-phycom && cd substrate-phycom

PYTHONPATH=. python -m integration.demo             # two carriers, one seed
PYTHONPATH=. python -m integration.demo_regenerate  # does the message come back?
PYTHONPATH=. python -m integration.demo_failures    # what the gate does when wrong

PYTHONPATH=. python tests/test_stack.py             # 47 contract tests
PYTHONPATH=. python tests/test_legacy.py            # 17 golden vectors + ledger
python tools/check_stdlib_only.py                   # the no-deps rule, enforced
```

## Use it

```python
from core.seed import Seed, seed_from_message
from expanders.geomagnetic import GeomagneticExpander, FieldModel

# The shared model. Agreed out of band; never transmitted.
field = FieldModel(
    declination_deg=-1.6,       # plug a real WMM/IGRF value for your place
    inclination_deg=74.8,
    intensity_nt=57200.0,
    anchor="shield-anchor-01",
)
geo = GeomagneticExpander(field)

# Fold a message to a seed, send the seed, expand on the far side.
seed = seed_from_message(b"meet at the north cache", geo.model_id, epoch=42)
wire = seed.to_wire()                       # 40 bytes — this is all that travels
schedule = geo.expand(Seed.from_wire(wire), steps=64)

# A peer without the field model expands the same seed to unrelated noise,
# and gets no signal that it was close.
```

Swap `GeomagneticExpander` for `OrbitalExpander` and the same seed rides
a different carrier with no other change. That is the whole point of the
layer.

## What the seed actually buys you

Read this before building on it — the headline claim is narrower than it
sounds, and the narrowing is [F-13](NOTEBOOK.md#round-2--this-round).

The reference fold is SHA-256 truncated to 120 bits. It is **one-way**:
`expand()` returns floats, and no expander here reconstructs a message
from them. There are two regimes in which the shared model gets a
message across, and they trade off:

| | **A: shared codebook** | **B: physics-keyed pad** |
|---|---|---|
| on the wire | seed only (40 B) | seed + message-sized ciphertext |
| message space | shared, enumerable | arbitrary |
| compresses? | **yes** | no |
| gated by | not holding the codebook | not holding the model |

Both run in `integration/demo_regenerate.py`. The shared model is the
gate in both. The *compression* claim holds only in regime A, where the
message already exists at the far end.

## Layout

```
core/seed.py        the unit crossing every layer — 120-bit payload,
                    model_id, 16-bit epoch, CRC16
core/expander.py    the abstraction this repo adds. Same seed in,
                    deterministic schedule out.
expanders/orbital.py      reference adapter to orbital-phycom (Kepler)
expanders/geomagnetic.py  terrestrial field-model expander (the new piece)
expanders/template.py     copy this to add a carrier
integration/        three runnable demos: happy path, regeneration, failure modes
tests/              determinism, round-trip, the gate, golden vectors
legacy/             retired modes, still executable. Precedent carries.
NOTEBOOK.md         what was claimed, what was run, what fell over
```

## Core invariant

> Same seed + same model + same epoch = identical output. Forever.

"Forever" is load-bearing. A seed minted under a mode that was later
superseded still has to expand the same way, so retired behaviour is
[quarantined, not deleted](legacy/README.md), and every retired mode has
a golden vector pinning its exact bytes.

Anything that changes the output must change the `model_id`. Two peers
who disagree should be *rejected*, never silently divergent.

## Adding a carrier

One file. `cp expanders/template.py expanders/mycarrier.py` and satisfy
four obligations — the template spells them out, and the test suite
checks the template itself so it cannot rot.

## How this repo is developed

Hypothesize, run, record, falsify, edit the claim, name the unknowns,
rerun. [`NOTEBOOK.md`](NOTEBOOK.md) is the ledger: fourteen findings,
what each one killed, and a list of **open unknowns** that are honestly
still open — including [U-6](NOTEBOOK.md#u-6), which argues the
geomagnetic field is doing less cryptographic work than this module's
prose implies.

Falsified claims are not deleted. They are kept next to what replaced
them, because the reasoning is the part that gets lost.

## License

CC0 1.0 Universal — public domain. No extraction, no attribution
required, no permission needed.
