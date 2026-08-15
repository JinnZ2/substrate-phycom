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
  <your physics here> -> expanders/template.py

stdlib only.

Retired mode honoured here: KEYSTREAM_ABS_MOD (see legacy/modes.py, F-11).
Full ledger: NOTEBOOK.md
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from core.seed import Seed
from legacy.modes import KEYSTREAM_ABS_MOD

KEYSTREAM_SIGNED = "signed"  # int((v + 1.0) * 127.5) & 0xFF — maps [-1,1] to [0,255]

__all__ = ["Expander", "ModelMismatch", "KEYSTREAM_SIGNED", "KEYSTREAM_ABS_MOD"]


class ModelMismatch(ValueError):
    """Raised when an Expander is asked to unfold a seed minted for a
    different model. Loud beats silent: without this, a mismatched pair
    expands happily and produces garbage that looks like a schedule."""


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

        steps=0 returns []. This method does NOT check model_id — the
        gate demos need to show what a mismatch actually sounds like.
        Use expand_strict() in anything that should fail loudly.
        """
        ...

    def expand_strict(self, seed: Seed, steps: int) -> List[float]:
        """expand(), but refuse a seed this model cannot legitimately
        unfold. Use this at any real boundary; a mismatched model_id is
        a protocol error, not a source of interesting noise.

        Note the limit of the check: model_id is carried in the clear on
        the wire, so it proves agreement on *which* model, never on the
        model's parameters. Two peers with the same model_id and
        different FieldModels pass this check and still diverge — that
        divergence is the gate, and it is supposed to be silent.
        """
        if not self.accepts(seed):
            raise ModelMismatch(
                f"seed is for model_id {seed.model_id!r}; "
                f"this expander unfolds {self.model_id!r}"
            )
        return self.expand(seed, steps)

    def keystream(self, seed: Seed, n_bytes: int, *, fold: str = KEYSTREAM_SIGNED) -> bytes:
        """Derive a byte keystream from the expanded schedule.

        fold=KEYSTREAM_SIGNED (default): int((v + 1.0) * 127.5) & 0xFF
            Maps [-1, 1] linearly to [0, 255]; sign is preserved.

        fold=KEYSTREAM_ABS_MOD: legacy, retired. Discards the sign of v
            (v and -v give the same byte). See legacy/modes.py F-11.

        Lets any expander double as a physics-keyed pad without extra
        code — which is the only regime in this repo that moves an
        arbitrary message end to end. See NOTEBOOK.md F-13.
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

    def model_key(self) -> bytes:
        """Secret material this model holds that never crosses the wire.

        Pass it to seed_from_message(key=...) to key the fold, which is
        what gives regime A a gate when the codebook is public (F-16).

        Returns b"" here, meaning *this expander offers no secret* — and
        that is the honest answer for OrbitalExpander, whose parameters
        (periods, sample_rate, modes) are all either public or encoded
        in model_id. An expander whose model is genuinely private
        overrides this; GeomagneticExpander and TemplateExpander do.

        Read F-17 before treating a returned key as strong. A
        geomagnetic model key derived only from published field values
        is worth about 2^21 against someone who knows your county — it
        is a salt that makes the search per-place, not a key.
        """
        return b""
