"""
expander.py — the abstraction this repo adds.

orbital-phycom proved one expander (Kepler + perturbations).
BE2 made transport pluggable.
This makes the EXPANDER pluggable.

An Expander is any deterministic, shared physics model that turns a
small seed into a large schedule/keystream/message. Both ends must run
the SAME expander with the SAME model parameters. That shared model is
the thing that does not travel over the wire — and so it is both the
compression (you don't send what physics can regenerate) and the
gate (no shared model, no message).

  orbital mechanics   -> expanders/orbital.py
  geomagnetic + field -> expanders/geomagnetic.py
  <your physics here> -> implement Expander

stdlib only.

--- AUDIT FINDINGS ADDRESSED ---
Finding 11: abs() in keystream() discards the sign of every schedule
            value, halving effective entropy per sample. Two modes are
            now explicit:
            KEYSTREAM_ABS_MOD — original; sign discarded (legacy).
            KEYSTREAM_SIGNED  — maps [-1,1] to [0,255]; sign preserved (default).
Finding 10: expand(seed, 0) guard note — max(1, n_bytes) in keystream
            means steps=0 is never passed from this path; documented.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from core.seed import Seed


# keystream byte-fold choices (Finding 11)
KEYSTREAM_ABS_MOD = "abs_mod"  # int(abs(v) * 1e6) & 0xFF — sign discarded; legacy
KEYSTREAM_SIGNED  = "signed"   # int((v + 1.0) * 127.5) & 0xFF — maps [-1,1] to [0,255]


class Expander(ABC):
    """Deterministic seed -> schedule. The physics IS the decompressor."""

    #: must match the Seed.model_id this expander can unfold
    model_id: str = "abstract"

    @abstractmethod
    def expand(self, seed: Seed, steps: int) -> List[float]:
        """Unfold a seed into `steps` real-valued schedule points.

        Determinism is the contract: same seed + same model params +
        same epoch -> identical output, on any machine, with no further
        communication.

        steps=0 returns []. steps=1 returns one point; note that
        OrbitalExpander uses max(steps,1) as denominator so t=epoch
        in that degenerate case — avoid if epoch is large.
        """
        ...

    def keystream(self, seed: Seed, n_bytes: int, *, fold: str = KEYSTREAM_SIGNED) -> bytes:
        """Derive a byte keystream from the expanded schedule.

        fold=KEYSTREAM_SIGNED (default): int((v + 1.0) * 127.5) & 0xFF
            Maps [-1, 1] linearly to [0, 255]; sign is preserved.

        fold=KEYSTREAM_ABS_MOD: int(abs(v) * 1e6) & 0xFF
            Original behaviour. Discards the sign of v: v and -v map
            to the same byte. Halves the information per sample.
            (Finding 11: conceptual sign loss, though byte-bias is
            negligible due to the * 1e6 scramble.)

        Lets any expander double as a physics-keyed pad without extra code.
        """
        vals = self.expand(seed, max(1, n_bytes))
        out = bytearray()
        for v in vals:
            if fold == KEYSTREAM_ABS_MOD:
                out.append(int(abs(v) * 1e6) & 0xFF)
            else:  # KEYSTREAM_SIGNED
                out.append(int((v + 1.0) * 127.5) & 0xFF)
            if len(out) >= n_bytes:
                break
        return bytes(out[:n_bytes])

    def accepts(self, seed: Seed) -> bool:
        return seed.model_id == self.model_id
