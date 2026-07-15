"""
demo.py — the whole stack in one runnable file.

Shows the seam between all three repos:

  geometric-to-binary  ->  fold message to a SEED   (core/seed.py reference fold)
  BE2-communication    ->  carry the seed, transport-agnostic (simulated hop)
  orbital / geomagnetic->  PHYSICS expands the seed back   (expanders/)

The point being demonstrated: the message never crosses the wire. Only
the seed does. The far end regenerates the schedule from shared physics.
Swap the expander and the SAME seed rides a different carrier with no
other change.

Run:  PYTHONPATH=. python -m integration.demo
"""

from __future__ import annotations

from core.seed import seed_from_message, Seed
from expanders.orbital import OrbitalExpander
from expanders.geomagnetic import GeomagneticExpander, FieldModel, lattice_hash_from_axes


def simulated_transport_hop(wire: bytes, label: str) -> bytes:
    """Stand-in for BE2's transport layer. In the real stack this is
    LoRa / HAM / CB / UDP mesh — it does not care what it carries."""
    print(f"  [{label}] carrying {len(wire)} bytes of seed (not the message)")
    return wire  # bytes in, bytes out — transport is dumb on purpose


def run():
    message = b"meet at the north cache before the field flips"
    print(f"message to move: {message!r}  ({len(message)} bytes)\n")

    # ---- ORBITAL CARRIER ------------------------------------------------
    orb = OrbitalExpander()
    s1 = seed_from_message(message, model_id=orb.model_id, epoch=42)
    wire1 = s1.to_wire()
    print(f"orbital seed  : {s1.fingerprint()}  wire={len(wire1)}B")
    got1 = Seed.from_wire(simulated_transport_hop(wire1, "orbital/ΔV"))
    sched1 = orb.expand(got1, steps=8)
    print(f"  expanded schedule: {[round(x,3) for x in sched1]}\n")

    # ---- GEOMAGNETIC CARRIER (same message, ground physics) -------------
    # Shared field model: a place + (optionally) a physical crystal's axes.
    axes = [[1.0, 0.0, 0.2], [0.0, 1.0, -0.1], [0.2, -0.1, 1.0]]
    field = FieldModel(
        declination_deg=-1.6,      # e.g. northern MN, plug real WMM value
        inclination_deg=74.8,
        intensity_nt=57200.0,
        anchor="shield-anchor-01",
        lattice_hash=lattice_hash_from_axes(axes),
    )
    geo = GeomagneticExpander(field)
    s2 = seed_from_message(message, model_id=geo.model_id, epoch=42)
    wire2 = s2.to_wire()
    print(f"geomag seed   : {s2.fingerprint()}  wire={len(wire2)}B")
    got2 = Seed.from_wire(simulated_transport_hop(wire2, "ground RF / CB / HAM"))
    sched2 = geo.expand(got2, steps=8)
    print(f"  expanded schedule: {[round(x,3) for x in sched2]}\n")

    # ---- THE GATE -------------------------------------------------------
    # Same seed, WRONG field model -> noise. No shared physics, no message.
    wrong = GeomagneticExpander(FieldModel(0.0, 0.0, 50000.0, "wrong-place"))
    noise = wrong.expand(got2, steps=8)
    print("observer without the field model expands the SAME seed to:")
    print(f"  {[round(x,3) for x in noise]}")
    print("\n-> bandwidth was never the bottleneck. The shared model is.")


if __name__ == "__main__":
    run()
