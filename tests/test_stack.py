"""Tests — determinism is the contract, so we test the contract."""

from core.seed import (
    Seed, seed_from_message, SEED_PAYLOAD_BYTES, WIRE_EPOCH_MAX,
    FOLD_FLAT, FOLD_SAFE,
)
from core.expander import KEYSTREAM_ABS_MOD, KEYSTREAM_SIGNED
from expanders.orbital import OrbitalExpander, T_NORMALIZED, T_ABSOLUTE, ENTROPY_PARTIAL, ENTROPY_FULL
from expanders.geomagnetic import GeomagneticExpander, FieldModel, lattice_hash_from_axes, KEY_V1, KEY_V2


# --- original contract tests (must still pass) ---

def test_seed_wire_roundtrip():
    s = seed_from_message(b"hello", "geomag.field.v1", epoch=7)
    assert Seed.from_wire(s.to_wire()) == s


def test_seed_payload_size():
    s = seed_from_message(b"x", "orbital.kepler.v1")
    assert len(s.payload) == SEED_PAYLOAD_BYTES


def test_orbital_deterministic():
    e = OrbitalExpander()
    s = seed_from_message(b"abc", e.model_id, epoch=1)
    assert e.expand(s, 16) == e.expand(s, 16)


def test_geomag_deterministic_same_model():
    f = FieldModel(-1.6, 74.8, 57200.0, "anchor")
    a, b = GeomagneticExpander(f), GeomagneticExpander(f)
    s = seed_from_message(b"abc", "geomag.field.v1", epoch=2)
    assert a.expand(s, 16) == b.expand(s, 16)


def test_geomag_gate_wrong_model_diverges():
    s = seed_from_message(b"abc", "geomag.field.v1", epoch=2)
    right = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "right"))
    wrong = GeomagneticExpander(FieldModel(0.0, 0.0, 50000.0, "wrong"))
    assert right.expand(s, 16) != wrong.expand(s, 16)


# --- Finding 1 / Finding 8: epoch range enforcement ---

def test_epoch_out_of_range_rejected():
    payload = bytes(SEED_PAYLOAD_BYTES)
    try:
        Seed(payload, "m", epoch=WIRE_EPOCH_MAX + 1)
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_epoch_negative_rejected():
    payload = bytes(SEED_PAYLOAD_BYTES)
    try:
        Seed(payload, "m", epoch=-1)
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_epoch_boundary_accepted():
    payload = bytes(SEED_PAYLOAD_BYTES)
    Seed(payload, "m", epoch=0)
    Seed(payload, "m", epoch=WIRE_EPOCH_MAX)


# --- Finding 2: seed_from_message fold modes ---

def test_fold_flat_ambiguous_pair_collision():
    # (b"ab","c") and (b"a","bc") have the same flat hash input
    s1 = seed_from_message(b"ab", "c", fold=FOLD_FLAT)
    s2 = seed_from_message(b"a", "bc", fold=FOLD_FLAT)
    assert s1.payload == s2.payload  # confirms the known collision


def test_fold_safe_resolves_ambiguity():
    s1 = seed_from_message(b"ab", "c", fold=FOLD_SAFE)
    s2 = seed_from_message(b"a", "bc", fold=FOLD_SAFE)
    assert s1.payload != s2.payload


def test_fold_safe_still_deterministic():
    s1 = seed_from_message(b"hello", "orbital.kepler.v1", epoch=5, fold=FOLD_SAFE)
    s2 = seed_from_message(b"hello", "orbital.kepler.v1", epoch=5, fold=FOLD_SAFE)
    assert s1.payload == s2.payload


# --- Finding 3: FieldModel.key() collision ---

def test_key_v1_collision():
    # anchor="abc", lattice_hash="" vs anchor="ab", lattice_hash="c"
    f1 = FieldModel(0.0, 0.0, 50000.0, "abc", lattice_hash="", key_version=KEY_V1)
    f2 = FieldModel(0.0, 0.0, 50000.0, "ab",  lattice_hash="c", key_version=KEY_V1)
    assert f1.key() == f2.key()  # confirms the known collision


def test_key_v2_no_collision():
    f1 = FieldModel(0.0, 0.0, 50000.0, "abc", lattice_hash="", key_version=KEY_V2)
    f2 = FieldModel(0.0, 0.0, 50000.0, "ab",  lattice_hash="c", key_version=KEY_V2)
    assert f1.key() != f2.key()


# --- Finding 4: OrbitalExpander t_mode ---

def test_t_normalized_shape_changes_with_steps():
    e = OrbitalExpander(t_mode=T_NORMALIZED)
    s = seed_from_message(b"x", e.model_id, epoch=0)
    short = e.expand(s, 3)
    full  = e.expand(s, 10)
    # first elements share t=0 so they're equal, but second differs
    assert short[0] == full[0]
    assert short[1] != full[1]


def test_t_absolute_prefix_consistent():
    e = OrbitalExpander(t_mode=T_ABSOLUTE)
    s = seed_from_message(b"x", e.model_id, epoch=0)
    short = e.expand(s, 3)
    full  = e.expand(s, 10)
    assert short == full[:3]


# --- Finding 5: OrbitalExpander entropy modes ---

def test_entropy_partial_ignores_most_bytes():
    e = OrbitalExpander(entropy=ENTROPY_PARTIAL)
    # two seeds identical in bytes 0-2, different elsewhere
    p1 = bytes([10, 20, 30] + [0] * 12)
    p2 = bytes([10, 20, 30] + [99] * 12)
    s1 = Seed(p1, e.model_id, epoch=0)
    s2 = Seed(p2, e.model_id, epoch=0)
    assert e.expand(s1, 8) == e.expand(s2, 8)  # bytes 3-14 had no effect


def test_entropy_full_uses_all_bytes():
    e = OrbitalExpander(entropy=ENTROPY_FULL)
    p1 = bytes([10, 20, 30] + [0] * 12)
    p2 = bytes([10, 20, 30] + [99] * 12)
    s1 = Seed(p1, e.model_id, epoch=0)
    s2 = Seed(p2, e.model_id, epoch=0)
    assert e.expand(s1, 8) != e.expand(s2, 8)


# --- Finding 9: from_wire short input ---

def test_from_wire_too_short_raises_value_error():
    try:
        Seed.from_wire(b"\x00" * 5)
        assert False, "should have raised ValueError"
    except ValueError:
        pass


# --- Finding 11: keystream fold modes ---

def test_keystream_abs_mod_loses_sign():
    f = FieldModel(-1.6, 74.8, 57200.0, "a")
    geo = GeomagneticExpander(f)
    s = seed_from_message(b"test", "geomag.field.v1", epoch=0)
    # abs_mod: sign discarded; test that the fold at least runs
    ks = geo.keystream(s, 8, fold=KEYSTREAM_ABS_MOD)
    assert len(ks) == 8


def test_keystream_signed_distinct_from_abs_mod():
    f = FieldModel(-1.6, 74.8, 57200.0, "a")
    geo = GeomagneticExpander(f)
    s = seed_from_message(b"test", "geomag.field.v1", epoch=0)
    ks_abs = geo.keystream(s, 16, fold=KEYSTREAM_ABS_MOD)
    ks_sig = geo.keystream(s, 16, fold=KEYSTREAM_SIGNED)
    # different fold methods; outputs will generally differ
    assert ks_abs != ks_sig


# --- lattice_hash_from_axes structure ---

def test_lattice_hash_v1_loses_structure():
    assert lattice_hash_from_axes([[1.0, 2.0]], version=1) == \
           lattice_hash_from_axes([[1.0], [2.0]], version=1)


def test_lattice_hash_v2_preserves_structure():
    assert lattice_hash_from_axes([[1.0, 2.0]], version=2) != \
           lattice_hash_from_axes([[1.0], [2.0]], version=2)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
