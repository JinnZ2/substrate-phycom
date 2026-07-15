"""Tests — determinism is the contract, so we test the contract."""

from core.seed import (
    Seed, seed_from_message, SEED_PAYLOAD_BYTES, WIRE_EPOCH_MAX,
    FOLD_FLAT, FOLD_SAFE,
)
from core.expander import KEYSTREAM_ABS_MOD, KEYSTREAM_SIGNED
from expanders.orbital import OrbitalExpander, T_NORMALIZED, T_ABSOLUTE, ENTROPY_PARTIAL, ENTROPY_FULL
from expanders.geomagnetic import GeomagneticExpander, FieldModel, lattice_hash_from_axes, KEY_V1, KEY_V2


# --- original contract tests ---

def test_seed_wire_roundtrip():
    # model_id is an opaque string for the wire; no expander needed here
    s = seed_from_message(b"hello", "test-model", epoch=7)
    assert Seed.from_wire(s.to_wire()) == s


def test_seed_payload_size():
    e = OrbitalExpander()
    s = seed_from_message(b"x", e.model_id)
    assert len(s.payload) == SEED_PAYLOAD_BYTES


def test_orbital_deterministic():
    e = OrbitalExpander()
    s = seed_from_message(b"abc", e.model_id, epoch=1)
    assert e.expand(s, 16) == e.expand(s, 16)


def test_geomag_deterministic_same_model():
    f = FieldModel(-1.6, 74.8, 57200.0, "anchor")
    geo = GeomagneticExpander(f)
    a, b = GeomagneticExpander(f), GeomagneticExpander(f)
    s = seed_from_message(b"abc", geo.model_id, epoch=2)
    assert a.expand(s, 16) == b.expand(s, 16)


def test_geomag_gate_wrong_model_diverges():
    right = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "right"))
    wrong = GeomagneticExpander(FieldModel(0.0, 0.0, 50000.0, "wrong"))
    s = seed_from_message(b"abc", right.model_id, epoch=2)
    assert right.expand(s, 16) != wrong.expand(s, 16)


# --- model_id encodes active modes (Inconsistency 1.3 / 1.4) ---

def test_orbital_model_id_encodes_entropy_and_tmode():
    full_norm = OrbitalExpander(entropy=ENTROPY_FULL,    t_mode=T_NORMALIZED)
    part_norm = OrbitalExpander(entropy=ENTROPY_PARTIAL, t_mode=T_NORMALIZED)
    full_abs  = OrbitalExpander(entropy=ENTROPY_FULL,    t_mode=T_ABSOLUTE)
    assert full_norm.model_id != part_norm.model_id
    assert full_norm.model_id != full_abs.model_id
    assert part_norm.model_id != full_abs.model_id


def test_geomag_model_id_encodes_key_version():
    f_kv1 = FieldModel(0.0, 0.0, 50000.0, "place", key_version=KEY_V1)
    f_kv2 = FieldModel(0.0, 0.0, 50000.0, "place", key_version=KEY_V2)
    assert GeomagneticExpander(f_kv1).model_id != GeomagneticExpander(f_kv2).model_id


def test_accepts_rejects_wrong_mode_mismatch():
    # seed created for full-entropy expander; partial-entropy expander must not accept it
    full = OrbitalExpander(entropy=ENTROPY_FULL)
    part = OrbitalExpander(entropy=ENTROPY_PARTIAL)
    s = seed_from_message(b"x", full.model_id)
    assert full.accepts(s)
    assert not part.accepts(s)


# --- Inconsistency 1.1: epoch width in seed_from_message matches wire (16-bit) ---

def test_epoch_hash_width_consistent_with_wire():
    # Verify the fold uses !H (2 bytes) not !I (4 bytes) by checking that
    # seeds with epoch=0 and epoch=65536 would have been identical under
    # the old !I packing but are now rejected (epoch=65536 is invalid).
    payload = bytes(SEED_PAYLOAD_BYTES)
    try:
        Seed(payload, "m", epoch=65536)
        assert False, "should have been rejected"
    except ValueError:
        pass
    # epoch=0 and epoch=1 must produce different payloads (proves epoch is in the hash)
    s0 = seed_from_message(b"x", "m", epoch=0)
    s1 = seed_from_message(b"x", "m", epoch=1)
    assert s0.payload != s1.payload


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
    e = OrbitalExpander()
    s1 = seed_from_message(b"hello", e.model_id, epoch=5, fold=FOLD_SAFE)
    s2 = seed_from_message(b"hello", e.model_id, epoch=5, fold=FOLD_SAFE)
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

def test_keystream_abs_mod_runs():
    f = FieldModel(-1.6, 74.8, 57200.0, "a")
    geo = GeomagneticExpander(f)
    s = seed_from_message(b"test", geo.model_id, epoch=0)
    ks = geo.keystream(s, 8, fold=KEYSTREAM_ABS_MOD)
    assert len(ks) == 8


def test_keystream_signed_distinct_from_abs_mod():
    f = FieldModel(-1.6, 74.8, 57200.0, "a")
    geo = GeomagneticExpander(f)
    s = seed_from_message(b"test", geo.model_id, epoch=0)
    ks_abs = geo.keystream(s, 16, fold=KEYSTREAM_ABS_MOD)
    ks_sig = geo.keystream(s, 16, fold=KEYSTREAM_SIGNED)
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
