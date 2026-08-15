"""
demo_regenerate.py — does the message actually come back?

integration/demo.py shows a seed crossing a wire and expanding into a
schedule. It never shows the message being regenerated, and the core
claim is:

    You transmit the SEED, not the message. A shared deterministic
    physics model regenerates the message.

Taken literally, that claim is false for this repo's reference fold.
seed_from_message is SHA-256 truncated to 120 bits — one-way. expand()
returns floats. No amount of shared physics inverts a hash. (F-13.)

What is true is narrower and more useful. There are exactly two regimes
in which the shared model gets a message to the far end, and they trade
off against each other. Both run below.

    PYTHONPATH=. python -m integration.demo_regenerate
"""

from __future__ import annotations

from typing import List, Optional

from core.expander import Expander
from core.seed import Seed, seed_from_message
from expanders.geomagnetic import FieldModel, GeomagneticExpander


# --- REGIME A: the seed SELECTS from a shared message space ----------

def codebook_recover(
    seed: Seed, codebook: List[bytes], model_id: str, epoch: int
) -> Optional[bytes]:
    """Regenerate the message by re-folding every candidate the far end
    already holds and matching payloads.

    This is the regime that actually compresses: 15 bytes on the wire
    regenerate a message of any length. It works because the message
    space is shared, finite, and agreed out of band — the codebook is
    part of the model, and the model does not travel.

    The cost is the constraint: you cannot send a message that is not
    already in the codebook. Search is O(len(codebook)) folds, which is
    trivial for a hundred entries and impossible for open text.

    An observer who lacks the codebook holds a 120-bit hash of an
    unknown preimage. An observer who has it needs only the model_id
    and epoch, both of which are in the clear on the wire — so the
    codebook, not the seed, is the secret here.
    """
    for candidate in codebook:
        if seed_from_message(candidate, model_id, epoch).payload == seed.payload:
            return candidate
    return None


# --- REGIME B: the expander is a physics-keyed pad --------------------

def pad_apply(expander: Expander, seed: Seed, data: bytes) -> bytes:
    """XOR data against the expander's keystream. Self-inverse: run it
    twice with the same (expander, seed) and you are back where you
    started.

    This regime carries an arbitrary message, and the shared model is a
    real gate — without the FieldModel the keystream is unrelated bytes.

    The cost is the other constraint: the ciphertext is as long as the
    message, so this buys secrecy, not compression. The claim "you
    transmit the seed, not the message" does not hold here; you
    transmit the seed AND a message-sized payload.

    Note also what this is not: a keystream derived deterministically
    from a fixed model and a 16-bit epoch repeats whenever (seed, epoch)
    repeats. Reusing a pad across two messages is the classic break.
    Treat epoch as a nonce and never mint two messages under one.
    """
    return bytes(a ^ b for a, b in zip(data, expander.keystream(seed, len(data))))


def run():
    field = FieldModel(
        declination_deg=-1.6,
        inclination_deg=74.8,
        intensity_nt=57200.0,
        anchor="shield-anchor-01",
    )
    geo = GeomagneticExpander(field)
    wrong = GeomagneticExpander(FieldModel(0.0, 0.0, 50000.0, "wrong-place"))
    message = b"meet at the north cache before the field flips"
    epoch = 42

    print("=== the literal claim ===")
    s = seed_from_message(message, geo.model_id, epoch)
    sched = geo.expand(s, 8)
    print(f"message   : {message!r} ({len(message)}B)")
    print(f"seed      : {s.fingerprint()} ({len(s.to_wire())}B on the wire)")
    print(f"expand()  : {[round(x, 3) for x in sched]}")
    print("            -> floats. The message is not in there and cannot be.\n")

    print("=== REGIME A: shared codebook, seed selects ===")
    codebook = [
        b"hold position",
        b"fall back to the ridge",
        b"meet at the north cache before the field flips",
        b"abort, go dark",
    ]
    got = codebook_recover(s, codebook, geo.model_id, epoch)
    print(f"recovered : {got!r}")
    print(f"exact     : {got == message}")
    print(f"on wire   : {len(s.to_wire())}B carried a {len(message)}B message")
    blind = codebook_recover(s, [c for c in codebook if c != message], geo.model_id, epoch)
    print(f"without the codebook entry: {blind!r}  <- no shared space, no message\n")

    print("=== REGIME B: physics-keyed pad, arbitrary message ===")
    ct = pad_apply(geo, s, message)
    print(f"ciphertext: {ct[:16].hex()}...  ({len(ct)}B — same size as the message)")
    print(f"recovered : {pad_apply(geo, s, ct)!r}")
    print(f"wrong model recovers: {pad_apply(wrong, s, ct)[:24]!r}\n")

    print("regime A compresses but needs a shared message space.")
    print("regime B carries anything but transmits message-sized bytes.")
    print("the shared model is the gate in both. see NOTEBOOK.md F-13.")


if __name__ == "__main__":
    run()
