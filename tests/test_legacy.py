"""
test_legacy.py — precedent carries, and here is what enforces it.

Two jobs:

  1. GOLDEN VECTORS. Every retired mode is pinned to the exact output it
     produced when it was retired. A refactor that changes them fails
     here, whether or not anyone remembered the old mode existed. This
     is what makes "a seed minted under FOLD_FLAT still expands in 2034"
     a checked statement instead of a hope.

  2. LEDGER INTEGRITY. legacy/modes.py claims each retirement was caused
     by a named test. These assertions check that the named tests still
     exist, that every retired constant is still importable from the
     module that honours it, and that the re-export has not drifted from
     the definition site.

Run: PYTHONPATH=. python tests/test_legacy.py
"""

import core.expander as ce
import core.seed as cs
import expanders.geomagnetic as eg
import expanders.orbital as eo
import tests.test_stack as stack
from core.seed import Seed, seed_from_message
from expanders.geomagnetic import FieldModel, GeomagneticExpander, lattice_hash_from_axes
from expanders.orbital import OrbitalExpander
from expanders.template import TemplateExpander, TemplateModel
from legacy.modes import (
    ENTROPY_PARTIAL, FOLD_FLAT, KEY_V1, KEYSTREAM_ABS_MOD, LATTICE_V1,
    RETIRED, T_NORMALIZED, explain,
)

# Fixed inputs for every golden vector below. Do not edit these — a new
# case gets new inputs, it does not repurpose these.
FROZEN_PAYLOAD = bytes(range(15))
FROZEN_SEED = Seed(FROZEN_PAYLOAD, "frozen", epoch=7)
FROZEN_AXES = [[1.0, 0.0, 0.2], [0.0, 1.0, -0.1]]
FROZEN_FIELD = FieldModel(-1.6, 74.8, 57200.0, "anchor")

# Float paths are compared at 9 decimal places, not bit-for-bit. The
# hash-derived paths are exact bytes. See NOTEBOOK.md U-3: math.sin comes
# from the platform libm, so cross-machine bit-identity of the orbital
# expander is asserted by CLAUDE.md but has never actually been measured.
FLOAT_PLACES = 9


def _round(vals):
    return [round(v, FLOAT_PLACES) for v in vals]


# --- 1. golden vectors: retired modes ---------------------------------

def test_golden_fold_flat():
    s = seed_from_message(b"precedent", "test-model", 7, fold=FOLD_FLAT)
    assert s.payload.hex() == "d12d056c5f20b1b7f29730ea1638e8"


def test_golden_key_v1():
    f = FieldModel(-1.6, 74.8, 57200.0, "anchor", key_version=KEY_V1)
    assert f.key().hex() == \
        "7313e68efa7b7de37f4236c0d94a6f58f03e2658e79d1a4d5a79b87576f9fdea"


def test_golden_lattice_v1():
    assert lattice_hash_from_axes(FROZEN_AXES, version=LATTICE_V1) == \
        "87e9574a7621996fda7f4112d6c6e0b1"


def test_golden_orbital_legacy_modes():
    e = OrbitalExpander(entropy=ENTROPY_PARTIAL, t_mode=T_NORMALIZED)
    assert _round(e.expand(FROZEN_SEED, 8)) == [
        0.751409264, 0.606189295, 0.433660877, 0.25673026,
        0.096615442, -0.029985894, -0.112952224, -0.14973703,
    ]


def test_golden_keystream_abs_mod():
    geo = GeomagneticExpander(FROZEN_FIELD)
    assert geo.keystream(FROZEN_SEED, 16, fold=KEYSTREAM_ABS_MOD).hex() == \
        "108976af91745080e6c2289280241cba"


# --- 1b. golden vectors: current defaults -----------------------------
# Today's defaults are tomorrow's legacy. Pin them on the way in, so the
# next round inherits evidence instead of having to reconstruct it.

def test_golden_fold_safe():
    s = seed_from_message(b"precedent", "test-model", 7)
    assert s.payload.hex() == "29c9ad4b379d7f59b68ecdfe426040"


def test_golden_key_v2():
    assert FROZEN_FIELD.key().hex() == \
        "d117560dd5f3a6efc89ca1ae2ae0d04d42b86dd79c5119cb757c8e7a5efd8178"


def test_golden_lattice_v2():
    assert lattice_hash_from_axes(FROZEN_AXES) == "71904661c1770d87e73dcd5c235d86f0"


def test_golden_orbital_defaults():
    assert _round(OrbitalExpander().expand(FROZEN_SEED, 8)) == [
        0.402281026, 0.402387948, 0.402458935, 0.402493793,
        0.402492335, 0.402454379, 0.402379748, 0.402268271,
    ]


def test_golden_geomagnetic_defaults():
    assert _round(GeomagneticExpander(FROZEN_FIELD).expand(FROZEN_SEED, 8)) == [
        -0.125200275, 0.902281224, -0.892790112, 0.645807584,
        -0.690577554, -0.509300374, -0.652368963, -0.416128786,
    ]


def test_golden_keystream_signed():
    geo = GeomagneticExpander(FROZEN_FIELD)
    assert geo.keystream(FROZEN_SEED, 16).hex() == "6ff20dd1273e2c4aedbb2cad3337fb21"


def test_golden_template_expander():
    t = TemplateExpander(TemplateModel(1.5, "t"))
    assert _round(t.expand(FROZEN_SEED, 4)) == \
        [0.399099718, 0.84774548, 0.344808118, 0.762752728]


# --- 2. ledger integrity ----------------------------------------------

def test_every_retirement_names_a_test_that_exists():
    for name, r in RETIRED.items():
        assert hasattr(stack, r.falsified_by), (
            f"{name} cites tests/test_stack.py::{r.falsified_by}, "
            f"which no longer exists. Fix the ledger or restore the test."
        )
        assert callable(getattr(stack, r.falsified_by))


def test_every_retirement_is_fully_documented():
    for name, r in RETIRED.items():
        assert r.constant == name
        for field in ("honored_by", "superseded_by", "hypothesis", "verdict", "finding"):
            assert getattr(r, field), f"{name}.{field} is empty"
        assert r.finding.startswith("F-"), f"{name} has no NOTEBOOK.md entry id"


def test_retired_constants_still_reachable_from_honoring_modules():
    """Legacy is the definition site; the honouring modules re-export.
    If a re-export is dropped, old callers break silently on import."""
    for module, const, value in (
        (cs, "FOLD_FLAT", FOLD_FLAT),
        (ce, "KEYSTREAM_ABS_MOD", KEYSTREAM_ABS_MOD),
        (eg, "KEY_V1", KEY_V1),
        (eg, "LATTICE_V1", LATTICE_V1),
        (eo, "T_NORMALIZED", T_NORMALIZED),
        (eo, "ENTROPY_PARTIAL", ENTROPY_PARTIAL),
    ):
        assert hasattr(module, const), f"{module.__name__} dropped {const}"
        assert getattr(module, const) == value, \
            f"{module.__name__}.{const} drifted from legacy/modes.py"


def test_no_retired_mode_is_a_default():
    """The whole point of retiring a mode is that nobody gets it by
    accident. T_NORMALIZED was the default until round 2; this stops it
    happening again to anything else."""
    assert seed_from_message(b"x", "m").payload == \
        seed_from_message(b"x", "m", fold=cs.FOLD_SAFE).payload
    assert FieldModel(0.0, 0.0, 1.0, "a").key_version == eg.KEY_V2
    assert lattice_hash_from_axes(FROZEN_AXES) == \
        lattice_hash_from_axes(FROZEN_AXES, version=eg.LATTICE_V2)
    e = OrbitalExpander()
    assert e.t_mode == eo.T_ABSOLUTE
    assert e.entropy == eo.ENTROPY_FULL
    geo = GeomagneticExpander(FROZEN_FIELD)
    assert geo.keystream(FROZEN_SEED, 8) == \
        geo.keystream(FROZEN_SEED, 8, fold=ce.KEYSTREAM_SIGNED)


def test_explain_covers_every_retirement():
    for name in RETIRED:
        text = explain(name)
        assert name in text and "falsified by" in text
    try:
        explain("NOT_A_MODE")
        assert False, "should have raised KeyError"
    except KeyError:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
