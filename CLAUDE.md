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

# Determinism + gate unit tests (no test framework needed — has its own runner)
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

- **`core/seed.py`** — The one unit that crosses every layer. 120-bit payload (15 bytes) + `model_id` + `epoch` (16-bit on wire). Wire format: `[1 ver | 2 epoch_lo | 1 model_len] + model_id + payload + CRC-16/CCITT-FALSE`. The CRC family is the same as BE2's `udp_mesh_spec`, so a seed validated here validates there. `seed_from_message` is a reference fold (SHA-256 of `message + model_id + epoch`, first 15 bytes) so the repo runs end-to-end on stdlib alone — in real deployment the fold comes from `geometric-to-binary-computational-bridge`.
- **`core/expander.py`** — `Expander` ABC. Subclasses set `model_id` and implement `expand(seed, steps) -> List[float]`. Determinism is the hard contract: same seed + same model params + same epoch → identical output on any machine with no further communication. `keystream(seed, n_bytes)` is provided free: folds the float schedule into bytes (`int(abs(v) * 1e6) & 0xFF`) so any expander doubles as a physics-keyed pad. `accepts(seed)` checks `seed.model_id == self.model_id`.
- **`expanders/orbital.py`** — Reference adapter to the orbital-phycom principle; **not a reimplementation**. `OrbitalExpander` (`model_id = "orbital.kepler.v1"`) encodes the 120-bit payload as per-channel phase offsets into prime-harmonic sinusoids (default periods `(2.0, 3.0, 5.0)`), summed and normalized. `epoch` shifts the time parameter coherently. The real engine (ΔV encoding, matched filtering, prime-harmonic constellations) lives in `orbital-phycom`.
- **`expanders/geomagnetic.py`** — The terrestrial expander. `FieldModel` holds `(declination_deg, inclination_deg, intensity_nt, anchor, lattice_hash)` agreed on out-of-band. `GeomagneticExpander.expand()` produces an HMAC-SHA256 stream keyed by `FieldModel.key()` and seeded by `seed.payload + epoch` — deterministic for anyone holding the same field model, noise for anyone who doesn't. `lattice_hash_from_axes` folds measured crystal/lattice axis vectors into a stable hash so a physical object seeds the model.
- **`integration/demo.py`** — End-to-end: same message → two seeds (orbital + geomagnetic, same `epoch=42`) → `simulated_transport_hop` (passthrough stand-in for BE2's transport; bytes in, bytes out, carrier-agnostic) → expand on far end → gate test (same seed + wrong `FieldModel` parameters → different, unrelated schedule).

### The gate property

Two parties sharing the same `Expander` instance (same physics model, same parameters) can expand a seed to the original message. A party with a different or missing model expands the same seed to noise. The gate is structural, not encrypted.

### Extending

- **New expander**: subclass `Expander` in `expanders/`, set `model_id`, implement `expand()`. Call `accepts(seed)` before expanding to guard against model_id mismatches. `keystream()` is inherited for free.
- **Field model sharpening**: `FieldModel` in `expanders/geomagnetic.py` is the plug point for real IGRF/WMM data or magnetometer readings.
- **Seed schema changes**: any change to `core/seed.py` wire format must stay compatible with BE2's CRC family and be coordinated across all four repos.

## License

CC0 1.0 Universal — public domain.
