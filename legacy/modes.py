"""
legacy/modes.py — retired modes. Still executable. That is the point.

PRECEDENT CARRIES.

Every identifier in this file was once the only behaviour, or the
default behaviour, of this stack. Each one was later falsified by a
test that is still in the suite. None of them were deleted, because
deleting them would break the one thing this repo sells:

    same seed + same model + same epoch = identical output, forever.

A seed minted in 2024 under FOLD_FLAT must still expand in 2034. So the
old dialect stays speakable. What changed is that it is no longer the
default and no longer the definition site: this file is, and every
module that still honours an old mode imports it from here. That makes
the whole legacy surface greppable in one command:

    grep -rn "legacy.modes" .

Do not select these for new work. `RETIRED` below records, for each one,
the claim that was made, the test that killed it, and what replaced it.
Full write-up per finding: ../NOTEBOOK.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# --- retired mode identifiers (this is their definition site) --------

FOLD_FLAT = "flat"
# core.seed.seed_from_message: message + model_id + epoch, no length prefix.

KEY_V1 = 1
# expanders.geomagnetic.FieldModel.key: anchor + lattice_hash, no length prefix.

LATTICE_V1 = 1
# expanders.geomagnetic.lattice_hash_from_axes: components hashed flat.

ENTROPY_PARTIAL = "partial"
# expanders.orbital.OrbitalExpander: phase from payload[ci % 15] only.

T_NORMALIZED = "normalized"
# expanders.orbital.OrbitalExpander: t = (k + epoch) / steps.

KEYSTREAM_ABS_MOD = "abs_mod"
# core.expander.Expander.keystream: int(abs(v) * 1e6) & 0xFF.


@dataclass(frozen=True)
class Retired:
    """One retired mode, with the evidence that retired it."""
    constant: str        # name of the identifier above
    value: object        # its wire/API value
    honored_by: str      # module that still accepts it
    superseded_by: str   # what to use instead
    hypothesis: str      # the claim as it was originally made
    falsified_by: str    # test in tests/test_stack.py that killed the claim
    finding: str         # entry id in NOTEBOOK.md
    verdict: str         # what the run actually showed


RETIRED: Dict[str, Retired] = {
    "FOLD_FLAT": Retired(
        constant="FOLD_FLAT",
        value=FOLD_FLAT,
        honored_by="core.seed.seed_from_message(fold=...)",
        superseded_by="core.seed.FOLD_SAFE",
        hypothesis="Concatenating message + model_id before hashing is "
                   "unambiguous, because model_id is a known fixed string.",
        falsified_by="test_fold_flat_ambiguous_pair_collision",
        finding="F-02",
        verdict="Falsified. (b'ab', 'c') and (b'a', 'bc') fold to the same "
                "payload. Safe only while model_id is fixed and trusted; "
                "structurally unsound the moment either is attacker-chosen.",
    ),
    "KEY_V1": Retired(
        constant="KEY_V1",
        value=KEY_V1,
        honored_by="expanders.geomagnetic.FieldModel(key_version=...)",
        superseded_by="expanders.geomagnetic.KEY_V2",
        hypothesis="anchor + lattice_hash is a unique key per place.",
        falsified_by="test_key_v1_collision",
        finding="F-03",
        verdict="Falsified. ('abc', '') and ('ab', 'c') derive the same HMAC "
                "key. lattice_hash defaults to '', so the collision class is "
                "reachable with ordinary anchor names — two different places "
                "silently share a channel.",
    ),
    "LATTICE_V1": Retired(
        constant="LATTICE_V1",
        value=LATTICE_V1,
        honored_by="expanders.geomagnetic.lattice_hash_from_axes(version=...)",
        superseded_by="expanders.geomagnetic.LATTICE_V2",
        hypothesis="Hashing axis components in order captures the geometry.",
        falsified_by="test_lattice_hash_v1_loses_structure",
        finding="F-03b",
        verdict="Falsified. [[a, b]] and [[a], [b]] hash identically — the "
                "vector count and per-vector arity are lost, so a 3x3 axis "
                "set and a 9x1 one are indistinguishable.",
    ),
    "ENTROPY_PARTIAL": Retired(
        constant="ENTROPY_PARTIAL",
        value=ENTROPY_PARTIAL,
        honored_by="expanders.orbital.OrbitalExpander(entropy=...)",
        superseded_by="expanders.orbital.ENTROPY_FULL",
        hypothesis="Taking one payload byte per channel spreads the seed's "
                   "120 bits across the expansion.",
        falsified_by="test_entropy_partial_ignores_most_bytes",
        finding="F-05",
        verdict="Falsified. With the default 3 periods only payload[0:3] is "
                "read: 12 of 15 bytes are silent, and the effective key space "
                "is 24 bits, not 120.",
    ),
    "T_NORMALIZED": Retired(
        constant="T_NORMALIZED",
        value=T_NORMALIZED,
        honored_by="expanders.orbital.OrbitalExpander(t_mode=...)",
        superseded_by="expanders.orbital.T_ABSOLUTE",
        hypothesis="t = (k + epoch) / steps is a time axis, so `steps` only "
                   "sets the resolution of the same schedule.",
        falsified_by="test_t_normalized_shape_changes_with_steps",
        finding="F-04",
        verdict="Falsified. expand(seed, 10)[:3] != expand(seed, 3) — `steps` "
                "rescales the axis, so it changes the schedule's shape, not "
                "its sampling. Also lets a large epoch slide the window "
                "without bound (F-06). Was the default until round 2.",
    ),
    "KEYSTREAM_ABS_MOD": Retired(
        constant="KEYSTREAM_ABS_MOD",
        value=KEYSTREAM_ABS_MOD,
        honored_by="core.expander.Expander.keystream(fold=...)",
        superseded_by="core.expander.KEYSTREAM_SIGNED",
        hypothesis="int(abs(v) * 1e6) & 0xFF is a fair fold of a schedule "
                   "point to a byte.",
        falsified_by="test_keystream_signed_distinct_from_abs_mod",
        finding="F-11",
        verdict="Partly falsified. abs() maps v and -v to the same byte, so "
                "one bit per sample is discarded by construction. The output "
                "byte distribution is not measurably biased (the 1e6 scale "
                "scrambles it), so this is an information loss, not an "
                "exploitable one.",
    ),
}


def explain(constant: str) -> str:
    """Human-readable provenance for a retired mode. Usable from a REPL:

        >>> from legacy.modes import explain
        >>> print(explain("KEY_V1"))
    """
    r = RETIRED.get(constant)
    if r is None:
        raise KeyError(
            f"{constant!r} is not a retired mode. Known: {sorted(RETIRED)}"
        )
    return (
        f"{r.constant} = {r.value!r}   [{r.finding}]\n"
        f"  honoured by  : {r.honored_by}\n"
        f"  use instead  : {r.superseded_by}\n"
        f"  claim made   : {r.hypothesis}\n"
        f"  falsified by : tests/test_stack.py::{r.falsified_by}\n"
        f"  what the run showed:\n    {r.verdict}"
    )


if __name__ == "__main__":
    for name in RETIRED:
        print(explain(name))
        print()
