"""
geomagnetic.py — the new piece, specific to this repo.

This is the terrestrial answer to orbital-phycom. Orbital-phycom uses
Kepler mechanics as the shared model both ends run. Up here on the
ground we use the LOCAL FIELD GEOMETRY as the shared model: the
geomagnetic vector at a place, the declination/inclination, and the
deterministic structure that crystal navigation has always read.

The tribal navigation insight, stated as engineering:

    A place has a field signature. Two parties who both know the field
    model of a region share a reference frame that never travels over
    the air. Transmit a seed over CB / HAM / LoRa / a knock on a pipe;
    the shared FIELD MODEL unfolds it into the message. An observer who
    does not hold the field model hears a seed that expands to noise.

So the satellite stops being the dependency. It becomes, at most, one
optional triangulation anchor that sharpens the field model. Pull it
and the channel still works, because the physics that does the
decompression is the ground you are standing on.

FieldModel below is deliberately pluggable and honest: it is keyed by
measurable field parameters. Plug in IGRF/WMM values, a magnetometer
reading, or a surveyed local anomaly map and the expansion sharpens.
Nothing here claims magic — it claims that a shared deterministic field
model is as good a decompressor as a shared orbit.

stdlib only.

--- AUDIT FINDINGS ADDRESSED ---
Finding 3: FieldModel.key() concatenated anchor + lattice_hash without
           a delimiter, so ("ab", "c") and ("a", "bc") produced the
           same HMAC key. Two key_version choices:
           KEY_V1 — flat concat; legacy, collision risk (especially when
                    lattice_hash="", the default).
           KEY_V2 — pack(len(anchor)) + anchor + lattice_hash;
                    unambiguous regardless of string lengths (default).

lattice_hash_from_axes: flat hash loses vector structure — [[a,b]] and
[[a],[b]] produced the same digest. version=2 (default) length-prefixes
each vector so structure is preserved.

Finding 1 impact: epoch in HMAC uses seed.epoch directly. Because
Seed.__post_init__ now enforces epoch ∈ [0, 0xFFFF], the HMAC input
is always consistent with what arrives from the wire. No separate
truncation needed here.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass
from typing import List

from core.seed import Seed
from core.expander import Expander


# FieldModel.key() derivation choices (Finding 3)
KEY_V1 = 1  # flat: anchor + lattice_hash — collision when one is a prefix of the other
KEY_V2 = 2  # length-prefixed anchor: pack(len(anchor)) + anchor + lattice_hash — unambiguous


@dataclass(frozen=True)
class FieldModel:
    """The shared, non-transmitted reference frame.

    These are the parameters two endpoints agree on out of band — by
    standing in the same region, by surveying it, by inheriting the
    same navigation knowledge. They are the 'orbit' of the ground.

    declination_deg : magnetic declination at the anchor (WMM/IGRF or measured)
    inclination_deg : magnetic inclination (dip)
    intensity_nt    : total field intensity, nanotesla
    anchor          : a stable label for the place / lattice / crystal axis set
    lattice_hash    : optional hash of a local anomaly map or crystal-axis
                      geometry. See lattice_hash_from_axes().
    key_version     : KEY_V1 (legacy) or KEY_V2 (default, unambiguous).
                      Two FieldModels with different key_version are
                      functionally distinct — they derive different HMAC keys.
    """
    declination_deg: float
    inclination_deg: float
    intensity_nt: float
    anchor: str
    lattice_hash: str = ""
    key_version: int = KEY_V2

    def key(self) -> bytes:
        raw = struct.pack(
            "!ddd",
            round(self.declination_deg, 3),
            round(self.inclination_deg, 3),
            round(self.intensity_nt, 1),
        )
        anchor_b = self.anchor.encode("utf-8")
        lh_b = self.lattice_hash.encode("utf-8")
        if self.key_version == KEY_V2:
            # length-prefixed: pack(len(anchor)) + anchor + lattice_hash
            # unambiguous regardless of string content or length (Finding 3)
            raw += struct.pack("!I", len(anchor_b)) + anchor_b + lh_b
        else:  # KEY_V1 — legacy; ("ab","c") == ("a","bc") == ("abc","")
            raw += anchor_b + lh_b
        return hashlib.sha256(raw).digest()


class GeomagneticExpander(Expander):
    model_id = "geomag.field.v1"

    def __init__(self, field: FieldModel):
        self.field = field
        self._mkey = field.key()

    def expand(self, seed: Seed, steps: int) -> List[float]:
        # The expansion is an HMAC stream keyed by the FIELD MODEL and
        # seeded by the payload. Deterministic for anyone holding the
        # same field model; noise for anyone who does not.
        # epoch is always in [0, 0xFFFF] (enforced by Seed.__post_init__),
        # so pack("!II", epoch, counter) is always valid.
        out: List[float] = []
        counter = 0
        buf = b""
        need = steps * 2  # 2 bytes per schedule point
        while len(buf) < need:
            block = hmac.new(
                self._mkey,
                seed.payload + struct.pack("!II", seed.epoch, counter),
                hashlib.sha256,
            ).digest()
            buf += block
            counter += 1
        for i in range(steps):
            word = struct.unpack("!H", buf[2 * i:2 * i + 2])[0]
            # word in [0, 65535]; divisor 32767.5 gives exact range [-1.0, +1.0]
            # (65535/32767.5 = 2.0 exactly). No word maps to 0.0.
            # Finding 7: range and symmetry verified correct.
            out.append((word / 32767.5) - 1.0)
        return out


def lattice_hash_from_axes(axes: List[List[float]], *, version: int = 2) -> str:
    """Fold a set of measured crystal/lattice axis vectors into a stable
    hash, so a physical reference object can seed the field model.

    version=1 (flat, legacy): hashes components in order with no
        structural markers. [[a, b]] and [[a], [b]] produce the same
        digest — the vector count and per-vector lengths are lost.

    version=2 (length-prefixed, default): packs len(vec) before each
        vector's components. [[a, b]] != [[a], [b]]. Structure is
        preserved. Use this for any new measurement.

    Both versions round each component to 6 decimal places before
    packing as a big-endian double.
    """
    h = hashlib.sha256()
    for vec in axes:
        if version == 2:
            h.update(struct.pack("!I", len(vec)))
        for c in vec:
            h.update(struct.pack("!d", round(c, 6)))
    return h.hexdigest()[:32]
