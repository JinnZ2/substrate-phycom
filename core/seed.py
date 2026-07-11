"""
seed.py — the unit that crosses every layer.

The whole stack runs on one idea: you do not transmit the message,
you transmit the SEED, and a shared physics model regenerates the
message on the far end. This module defines what a seed IS, so that
the encoder (geometric-to-binary), the transport (BE2), and the
expander (orbital / geomagnetic / whatever) all agree on the same
small object.

stdlib only. No deps. Phone-buildable.

--- AUDIT FINDINGS ADDRESSED ---
Finding 1: epoch silently truncated to 16 bits on wire; now enforced
           at construction so wire-format and expanders always agree.
Finding 2: seed_from_message concatenation ambiguous — FOLD_FLAT keeps
           legacy behaviour; FOLD_SAFE (default) length-prefixes the
           message so (message, model_id) boundaries are unambiguous.
Finding 8: negative epoch silently wrapped in to_wire and rejected by
           seed_from_message; now consistently rejected at construction.
Finding 9: from_wire raised struct.error on short input; now raises
           ValueError with a clear message before any unpacking.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Tuple


SEED_VERSION = 1
SEED_PAYLOAD_BYTES = 15       # 120 bits, matches orbital-phycom convention
WIRE_EPOCH_MAX     = 0xFFFF   # wire packs epoch as 2 bytes; construction rejects outside [0, WIRE_EPOCH_MAX]
MIN_WIRE_BYTES     = 4 + SEED_PAYLOAD_BYTES + 2  # header + empty model_id + payload + CRC = 21

# seed_from_message fold choices (Finding 2)
FOLD_FLAT = "flat"  # message + model_id.encode() + pack(epoch) — legacy; ambiguous at boundaries
FOLD_SAFE = "safe"  # pack(len(message)) + message + model_id.encode() + pack(epoch) — unambiguous


@dataclass(frozen=True)
class Seed:
    """A transmittable seed.

    payload   : the 120-bit core that the expander unfolds.
    model_id  : which shared physics model both ends must run to expand
                this. Two parties who do not share the same model_id
                cannot regenerate the message.
    epoch     : integer time anchor in [0, WIRE_EPOCH_MAX]. Keeps expansions
                deterministic and replay-distinct without clock sync.
                Constrained to 16 bits so wire-format and expander inputs
                are always consistent (Finding 1 / Finding 8).
    """
    payload: bytes
    model_id: str
    epoch: int = 0
    version: int = SEED_VERSION

    def __post_init__(self) -> None:
        if len(self.payload) != SEED_PAYLOAD_BYTES:
            raise ValueError(
                f"payload must be {SEED_PAYLOAD_BYTES} bytes, got {len(self.payload)}"
            )
        if not (0 <= self.epoch <= WIRE_EPOCH_MAX):
            raise ValueError(
                f"epoch must be in [0, {WIRE_EPOCH_MAX}]; got {self.epoch}. "
                f"Wire format is 16-bit; use epoch % WIRE_EPOCH_MAX if you need rollover."
            )

    # --- wire format -------------------------------------------------
    # header (1 ver | 2 epoch | 1 model_len) + model_id + payload + crc16
    def to_wire(self) -> bytes:
        mid = self.model_id.encode("utf-8")
        if len(mid) > 255:
            raise ValueError("model_id too long")
        head = struct.pack("!BHB", self.version, self.epoch, len(mid))
        body = head + mid + self.payload
        return body + struct.pack("!H", _crc16(body))

    @classmethod
    def from_wire(cls, data: bytes) -> "Seed":
        if len(data) < MIN_WIRE_BYTES:
            raise ValueError(
                f"wire packet too short: need ≥{MIN_WIRE_BYTES} bytes, got {len(data)}"
            )
        body, crc = data[:-2], data[-2:]
        if struct.unpack("!H", crc)[0] != _crc16(body):
            raise ValueError("CRC mismatch — seed corrupt")
        ver, epoch, mlen = struct.unpack("!BHB", body[:4])
        mid = body[4:4 + mlen].decode("utf-8")
        payload = body[4 + mlen:]
        return cls(payload=payload, model_id=mid, epoch=epoch, version=ver)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.to_wire()).hexdigest()[:12]


def _crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE. Same family BE2's udp_mesh_spec uses, so a
    seed validated here validates there. Verified against check value
    0x29B1 for the standard test vector b"123456789"."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def seed_from_message(
    message: bytes,
    model_id: str,
    epoch: int = 0,
    *,
    fold: str = FOLD_SAFE,
) -> "Seed":
    """Deterministically fold an arbitrary message down to a seed.

    fold=FOLD_SAFE (default): pack(len(message)) + message + model_id + pack(epoch).
        Unambiguous — different (message, model_id) pairs always produce
        different hash inputs regardless of where the boundary falls.

    fold=FOLD_FLAT: message + model_id.encode() + pack(epoch). Legacy.
        Ambiguous: seed_from_message(b"ab", "c", e) ==
                   seed_from_message(b"a", "bc", e). Safe when model_id
        is a fixed known string (e.g. "orbital.kepler.v1") since no
        real message will share that boundary, but structurally unsound.

    NOTE: this is the lossy/keyed direction. The expander + shared model
    is what unfolds it back. For a real deployment the fold is the
    geometric-to-binary encoder; this is the reference fold so the repo
    runs end-to-end with nothing but stdlib.
    """
    mid = model_id.encode("utf-8")
    epoch_bytes = struct.pack("!H", epoch)   # 16-bit, matching wire format (Finding 1.1)
    if fold == FOLD_SAFE:
        h_input = struct.pack("!I", len(message)) + message + mid + epoch_bytes
    else:  # FOLD_FLAT
        h_input = message + mid + epoch_bytes
    digest = hashlib.sha256(h_input).digest()
    return Seed(payload=digest[:SEED_PAYLOAD_BYTES], model_id=model_id, epoch=epoch)
