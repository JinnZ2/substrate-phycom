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

--- AUDIT FINDINGS ADDRESSED ---
Finding 4: t = (k + epoch) / steps meant steps changed the schedule
           *shape* (not just resolution): expand(seed,10)[:3] !=
           expand(seed,3). Two t_mode choices:
           T_NORMALIZED — original behaviour (default, backward-compat).
           T_ABSOLUTE   — t = (k + epoch) / sample_rate; fixed time
                          grid so steps only sets resolution, not shape.

Finding 5: only payload[0:len(periods)] (3 bytes) fed into phase
           derivation; 80% of seed entropy was silent. Two entropy
           choices:
           ENTROPY_PARTIAL — original; 3-byte effective key space (legacy).
           ENTROPY_FULL    — SHA-256(payload + channel_index) per channel;
                             all 120 seed bits influence every expansion (default).

Finding 6: large epoch shifts the T_NORMALIZED window unboundedly.
           T_ABSOLUTE is immune (epoch advances along a fixed time grid).
           Documented below.

Finding 12: t never reaches 1.0; no finite steps covers a full period.
            This is the correct DFT half-open convention. Documented.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import List

from core.seed import Seed
from core.expander import Expander


# t-computation choices (Finding 4 / Finding 6)
T_NORMALIZED = "normalized"
# t = (k + epoch) / steps
# The whole time axis is compressed into [epoch/steps, (epoch+steps-1)/steps).
# Changing steps changes the schedule shape, not just resolution.
# Large epoch shifts the window start unboundedly (Finding 6).
# Backward-compatible with original code.

T_ABSOLUTE = "absolute"
# t = (k + epoch) / sample_rate
# steps sets resolution only; shape is fixed by sample_rate.
# expand(seed,10)[:3] == expand(seed,3) when sample_rate is the same.
# Large epoch moves forward on a fixed time grid — epoch=256 is one
# full sample_rate period ahead of epoch=0.

# phase-derivation choices (Finding 5)
ENTROPY_PARTIAL = "partial"
# phase derived from payload[ci % 15] only.
# With 3 default periods, only payload[0..2] matter — 80% of entropy unused.
# Legacy. Effective key space: 24 bits.

ENTROPY_FULL = "full"
# phase derived from SHA-256(payload + pack(ci)) per channel.
# All 120 seed bits influence every channel's phase.
# Default.


class OrbitalExpander(Expander):
    model_id = "orbital.kepler.v1"
    DEFAULT_SAMPLE_RATE = 256.0

    def __init__(
        self,
        periods=(2.0, 3.0, 5.0),
        t_mode: str = T_NORMALIZED,
        sample_rate: float = DEFAULT_SAMPLE_RATE,
        entropy: str = ENTROPY_FULL,
    ):
        # prime-harmonic period ratios -> independent phase channels
        self.periods = tuple(periods)
        self.t_mode = t_mode
        self.sample_rate = sample_rate
        self.entropy = entropy

    def _t(self, k: int, epoch: int, steps: int) -> float:
        if self.t_mode == T_NORMALIZED:
            # half-open [epoch/steps, (epoch+steps-1)/steps)
            # t is epoch-relative; large epoch shifts the window (Finding 6)
            return (k + epoch) / max(steps, 1)
        else:  # T_ABSOLUTE
            return (k + epoch) / self.sample_rate

    def _phase(self, seed: Seed, ci: int) -> float:
        if self.entropy == ENTROPY_PARTIAL:
            # only payload[ci % 15] used; 12 of 15 bytes are silent (Finding 5)
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
