"""
template.py — copy this file to add a carrier.

The whole point of core/expander.py is that a new carrier costs you one
file. seed.py does not change. The BE2 transports do not change. Only
the physics changes.

    cp expanders/template.py expanders/mycarrier.py

Then satisfy four obligations:

  1. model_id must encode every parameter that changes the output.
     If two peers can configure your expander differently and still
     agree on model_id, the mismatch will not be caught by accepts()
     and they will diverge in silence. Encode the choice in the id.
     (This is why OrbitalExpander's id carries .efull.tabs.)

  2. expand() must be a pure function of (seed.payload, seed.epoch,
     your model parameters). No time.time(), no random, no os.urandom,
     no file or sensor reads at expansion time. Determinism is the
     contract; a single non-deterministic source voids it for everyone.

  3. Return values in [-1.0, 1.0]. keystream() folds that range to
     bytes; outside it, your keystream silently clips.

  4. steps=0 must return []. Anything else breaks the callers.

Measured, real-world inputs are welcome — but they belong in the MODEL
(fixed at construction, agreed out of band), never in expand(). The
model is the thing that does not cross the wire.

Nothing in this file is imported by the rest of the repo. It exists to
be copied, and it is exercised by tests/test_stack.py so it cannot rot.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass
from typing import List

from core.seed import Seed
from core.expander import Expander


@dataclass(frozen=True)
class TemplateModel:
    """The shared, non-transmitted reference frame for your carrier.

    Whatever both ends must already agree on for expansion to succeed:
    a place, an orbit, a field survey, a physical object's geometry.
    Frozen because a model that mutates is not a shared model.
    """
    parameter: float
    anchor: str

    def key(self) -> bytes:
        # Length-prefix anything variable-length before concatenating,
        # or ("ab", "c") and ("a", "bc") derive the same key. This is
        # the single most repeated mistake in this repo's history —
        # it was found twice, F-02 and F-03. Do not find it a third time.
        anchor_b = self.anchor.encode("utf-8")
        raw = struct.pack("!d", round(self.parameter, 6))
        raw += struct.pack("!I", len(anchor_b)) + anchor_b
        return hashlib.sha256(raw).digest()


class TemplateExpander(Expander):
    """Deterministic seed -> schedule for <your physics here>."""

    def __init__(self, model: TemplateModel):
        self.model = model
        self._mkey = model.key()
        # Obligation 1: every output-affecting choice goes in the id.
        self.model_id = "template.v1"

    def model_key(self) -> bytes:
        """Override only if your model holds something genuinely secret.
        Returning your derived key lets callers key the fold itself
        (`seed_from_message(key=...)`), which is what gates regime A
        when the codebook is public. Return b"" if your parameters are
        public — claiming a secret you do not have is worse than
        admitting you have none."""
        return self._mkey

    def expand(self, seed: Seed, steps: int) -> List[float]:
        # Obligation 4: steps=0 -> [] falls out of range(0) for free.
        out: List[float] = []
        buf = b""
        counter = 0
        while len(buf) < steps * 2:
            buf += hmac.new(
                self._mkey,
                seed.payload + struct.pack("!II", seed.epoch, counter),
                hashlib.sha256,
            ).digest()
            counter += 1
        for i in range(steps):
            word = struct.unpack("!H", buf[2 * i:2 * i + 2])[0]
            # Obligation 3: 65535 / 32767.5 == 2.0 exactly, so this
            # lands on [-1.0, +1.0] with both endpoints reachable.
            out.append((word / 32767.5) - 1.0)
        return out
