"""
orbital.py — reference adapter to orbital-phycom's principle.

This is NOT a reimplementation of orbital-phycom. It is the minimal
shared-physics expander that shows the seam: Kepler phase evolution as
a deterministic unfolder. The real engine, with ΔV encoding, matched
filtering, and prime-harmonic constellations, lives in:

    github.com/JinnZ2/orbital-phycom

Drop this in to satisfy the Expander contract when the carrier is
orbital deviation. Swap geomagnetic.py in when the carrier is ground RF.
Same seed, same schema — only the physics changes.

Retired modes honoured here: T_NORMALIZED (F-04/F-06), ENTROPY_PARTIAL
(F-05). See legacy/modes.py. Full ledger: NOTEBOOK.md

F-12 (held, not a defect): t never reaches 1.0, so no finite `steps`
covers a full period. That is the correct half-open DFT convention.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import List

from core.seed import Seed
from core.expander import Expander
from legacy.modes import T_NORMALIZED, ENTROPY_PARTIAL

T_ABSOLUTE = "absolute"
# t = (k + epoch) / sample_rate
# steps sets resolution only; shape is fixed by sample_rate.
# expand(seed,10)[:3] == expand(seed,3) when sample_rate is the same.
# Large epoch moves forward on a fixed time grid — epoch=256 is one
# full sample_rate period ahead of epoch=0. Default since round 2.

ENTROPY_FULL = "full"
# phase derived from SHA-256(payload + pack(ci)) per channel.
# All 120 seed bits influence every channel's phase. Default.


class OrbitalExpander(Expander):
    # model_id is an instance attribute (set in __init__) because it encodes
    # the active entropy and t_mode choices. Two OrbitalExpanders with
    # different modes have different model_ids, so accepts() and the gate
    # catch the mismatch automatically, rather than diverging in silence.
    DEFAULT_SAMPLE_RATE = 256.0

    def __init__(
        self,
        periods=(2.0, 3.0, 5.0),
        t_mode: str = T_ABSOLUTE,
        sample_rate: float = DEFAULT_SAMPLE_RATE,
        entropy: str = ENTROPY_FULL,
    ):
        # prime-harmonic period ratios -> independent phase channels
        self.periods = tuple(periods)
        self.t_mode = t_mode
        self.sample_rate = sample_rate
        self.entropy = entropy
        _e = "full" if entropy == ENTROPY_FULL else "part"
        _t = "abs"  if t_mode  == T_ABSOLUTE   else "norm"
        self.model_id = f"orbital.kepler.v1.e{_e}.t{_t}"

    def _t(self, k: int, epoch: int, steps: int) -> float:
        if self.t_mode == T_NORMALIZED:
            # retired: half-open [epoch/steps, (epoch+steps-1)/steps).
            # `steps` rescales the axis and a large epoch slides the
            # window without bound. legacy/modes.py, F-04 / F-06.
            return (k + epoch) / max(steps, 1)
        else:  # T_ABSOLUTE
            return (k + epoch) / self.sample_rate

    def _phase(self, seed: Seed, ci: int) -> float:
        if self.entropy == ENTROPY_PARTIAL:
            # retired: only payload[ci % 15] used; 12 of 15 bytes are
            # silent, so the key space is 24 bits. legacy/modes.py, F-05.
            ints = [b / 255.0 for b in seed.payload]
            return ints[ci % len(ints)] * 2.0 * math.pi
        else:  # ENTROPY_FULL
            # all 120 seed bits fold into each channel via SHA-256
            h = hashlib.sha256(seed.payload + struct.pack("!I", ci)).digest()
            return (struct.unpack("!H", h[:2])[0] / 65535.0) * 2.0 * math.pi

    def expand(self, seed: Seed, steps: int) -> List[float]:
        out: List[float] = []
        for k in range(steps):
            t = self._t(k, seed.epoch, steps)
            acc = 0.0
            for ci, P in enumerate(self.periods):
                phase0 = self._phase(seed, ci)
                acc += math.sin(2.0 * math.pi * t / P + phase0)
            out.append(acc / len(self.periods))
        return out
