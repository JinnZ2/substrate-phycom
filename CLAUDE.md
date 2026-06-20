# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

substrate-phycom is the connective seam of a four-repo physics-as-decompressor communication stack. The core idea: instead of transmitting a message, you transmit a **seed** and a **shared physics model** on both ends regenerates the message. The model never crosses the wire — that's simultaneously the compression and the access gate.

This repo's specific jobs:
1. Define the **one seed schema** (`core/seed.py`) that all four repos share on the wire.
2. Make the **expander layer pluggable** (`core/expander.py`) the same way BE2 made transport pluggable.
3. Provide the **terrestrial/geomagnetic expander** (`expanders/geomagnetic.py`) so the architecture works with no orbit.

## Running the code

```bash
# Full stack demo — same message, two carriers (orbital ΔV + ground RF), gate test
PYTHONPATH=. python -m integration.demo

# Determinism + gate unit tests
PYTHONPATH=. python tests/test_stack.py
```

`PYTHONPATH=.` is always required. No package installs — pure stdlib only; this must remain runnable on a phone.

## Architecture

```
MESSAGE
  │ fold to seed
  ▼
[SEED]  ──── 120-bit payload + model_id + epoch + CRC-16 ────► wire
                                                                  │
                                                                  ▼ physics expands seed
                                                              MESSAGE
```

### Four-repo stack

| Repo | Role |
|---|---|
| `geometric-to-binary-computational-bridge` | Encoder — folds a message to a seed (geometry → any substrate) |
| `orbital-phycom` | Proof expander — orbital mechanics (Kepler), ~6,944× compression |
| `BE2-communication` | Carrier — transport-agnostic mesh (TCP, UDP, LoRa, HAM, file, CB) |
| **substrate-phycom** (this repo) | Seam — pluggable expander abstraction + geomagnetic expander |

### Key files in this repo

- **`core/seed.py`** — The one unit that crosses every layer. 120-bit payload + `model_id` + epoch; CRC-16 wire format compatible with BE2's UDP mesh. Validates at both ends.
- **`core/expander.py`** — `Expander` abstract base. Any deterministic shared-physics model that can unfold a seed implements this interface.
- **`expanders/orbital.py`** — Thin reference adapter to the orbital-phycom principle (prime-harmonic Kepler phase). Real engine lives in orbital-phycom.
- **`expanders/geomagnetic.py`** — The terrestrial expander. `FieldModel` holds `(declination_deg, inclination_deg, intensity_nt, anchor, lattice_hash)` agreed on out-of-band. `GeomagneticExpander.expand()` produces an HMAC-SHA256 stream keyed by `FieldModel.key()` and seeded by `seed.payload + epoch` — deterministic for anyone holding the same field model, noise for anyone who doesn't. `lattice_hash_from_axes` folds measured crystal/lattice axis vectors into a stable hash so a physical object seeds the model.
- **`integration/demo.py`** — End-to-end: same message, two carriers, gate verification (wrong field model → noise).

### The gate property

Two parties sharing the same `Expander` instance (same physics model, same parameters) can expand a seed to the original message. A party with a different or missing model expands the same seed to noise. The gate is structural, not encrypted.

### Extending

- **New expander**: subclass `Expander` in `expanders/`, implement the deterministic unfold, register with a unique `model_id`.
- **Field model sharpening**: `FieldModel` in `expanders/geomagnetic.py` is the plug point for real IGRF/WMM data or magnetometer readings.
- **Seed schema changes**: any change to `core/seed.py` wire format must stay compatible with BE2's CRC family and be coordinated across all four repos.

## License

CC0 1.0 Universal — public domain.
