"""
demo_failures.py — what the gate does when something is wrong.

demo.py shows the happy path. The failure modes are where the design
actually lives, and they are not all the same shape. Three of them:

  1. corrupt seed        -> loud. CRC16 catches it at from_wire().
  2. wrong model_id      -> loud, if you ask. expand_strict() raises.
  3. wrong model PARAMS  -> silent, by design. Same model_id, different
                            FieldModel: the expansion just diverges.

(3) is the gate. It has to be silent — an observer who can tell "right
model, wrong parameters" apart from "wrong everything" has been handed
an oracle to grind against. Divergence without a signal is the point.

    PYTHONPATH=. python -m integration.demo_failures
"""

from __future__ import annotations

from core.expander import ModelMismatch
from core.seed import Seed, seed_from_message
from expanders.geomagnetic import FieldModel, GeomagneticExpander
from expanders.orbital import OrbitalExpander


def run():
    field = FieldModel(-1.6, 74.8, 57200.0, "shield-anchor-01")
    geo = GeomagneticExpander(field)
    message = b"meet at the north cache before the field flips"
    seed = seed_from_message(message, geo.model_id, epoch=42)
    wire = seed.to_wire()

    print("=== 1. corrupt seed: CRC16 rejects it ===")
    flipped = bytearray(wire)
    flipped[7] ^= 0x01  # one bit, mid-payload
    print(f"clean wire : {wire.hex()}")
    print(f"one bit off: {bytes(flipped).hex()}")
    try:
        Seed.from_wire(bytes(flipped))
        print("ACCEPTED — the CRC is not doing its job")
    except ValueError as e:
        print(f"rejected   : {e}")
    print()

    print("=== 2. wrong model_id: expand_strict refuses ===")
    orb = OrbitalExpander()
    print(f"seed is for : {seed.model_id}")
    print(f"expander is : {orb.model_id}")
    print(f"accepts()   : {orb.accepts(seed)}")
    loose = orb.expand(seed, 4)
    print(f"expand()    : {[round(x, 3) for x in loose]}  <- silent garbage")
    try:
        orb.expand_strict(seed, 4)
        print("expand_strict: ACCEPTED — the check is not doing its job")
    except ModelMismatch as e:
        print(f"expand_strict: {e}")
    print()

    print("=== 3. right model_id, wrong parameters: silent divergence ===")
    # Same class, same model_id, different field survey. Nothing in the
    # protocol can distinguish these two peers — and nothing should.
    other = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "different-anchor"))
    print(f"model_id match : {geo.model_id == other.model_id}")
    print(f"accepts()      : {other.accepts(seed)}")
    print(f"right params   : {[round(x, 3) for x in geo.expand(seed, 6)]}")
    print(f"wrong params   : {[round(x, 3) for x in other.expand(seed, 6)]}")
    print("no error is raised, and that is deliberate: an observer who")
    print("could tell 'close' from 'wrong' would have an oracle.")


if __name__ == "__main__":
    run()
