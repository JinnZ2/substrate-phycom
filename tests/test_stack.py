"""Tests — determinism is the contract, so we test the contract.

Golden vectors and the legacy ledger live in tests/test_legacy.py.

Run: PYTHONPATH=. python tests/test_stack.py
"""

from core.seed import (
    Seed, seed_from_message, SEED_PAYLOAD_BYTES, WIRE_EPOCH_MAX,
    FOLD_FLAT, FOLD_SAFE,
)
from core.expander import Expander, ModelMismatch, KEYSTREAM_ABS_MOD, KEYSTREAM_SIGNED
from expanders.orbital import OrbitalExpander, T_NORMALIZED, T_ABSOLUTE, ENTROPY_PARTIAL, ENTROPY_FULL
from expanders.geomagnetic import GeomagneticExpander, FieldModel, lattice_hash_from_axes, KEY_V1, KEY_V2
from expanders.template import TemplateExpander, TemplateModel
from integration.demo_regenerate import codebook_recover, pad_apply


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


# ======================================================================
# ROUND 2 — gaps the round-1 review named but did not close
# ======================================================================

# --- the contract, stated negatively: different inputs must diverge ---

def test_different_seeds_diverge():
    e = OrbitalExpander()
    a = seed_from_message(b"one", e.model_id, epoch=3)
    b = seed_from_message(b"two", e.model_id, epoch=3)
    assert a.payload != b.payload
    assert e.expand(a, 16) != e.expand(b, 16)


def test_different_epochs_diverge():
    """Same message, same model, different epoch -> different expansion.
    This is what makes a seed replay-distinct without a synced clock."""
    e = OrbitalExpander()
    a = seed_from_message(b"same", e.model_id, epoch=1)
    b = seed_from_message(b"same", e.model_id, epoch=2)
    assert a.payload != b.payload
    assert e.expand(a, 16) != e.expand(b, 16)

    # and the epoch must reach the expander, not just the fold: hold the
    # payload fixed and vary only the epoch that rides the wire.
    p = bytes(range(SEED_PAYLOAD_BYTES))
    geo = GeomagneticExpander(FieldModel(0.0, 0.0, 5e4, "a"))
    s1 = Seed(p, geo.model_id, epoch=1)
    s2 = Seed(p, geo.model_id, epoch=2)
    assert geo.expand(s1, 16) != geo.expand(s2, 16)
    assert OrbitalExpander().expand(s1, 16) != OrbitalExpander().expand(s2, 16)


def test_expansion_stays_in_unit_range():
    """keystream() folds [-1, 1] to bytes; anything outside clips."""
    p = bytes(range(SEED_PAYLOAD_BYTES))
    for e in (OrbitalExpander(), GeomagneticExpander(FieldModel(0.0, 0.0, 5e4, "a")),
              TemplateExpander(TemplateModel(1.0, "a"))):
        for v in e.expand(Seed(p, e.model_id, epoch=9), 256):
            assert -1.0 <= v <= 1.0, f"{e.model_id} produced {v}"


def test_steps_zero_returns_empty():
    p = bytes(range(SEED_PAYLOAD_BYTES))
    for e in (OrbitalExpander(), GeomagneticExpander(FieldModel(0.0, 0.0, 5e4, "a")),
              TemplateExpander(TemplateModel(1.0, "a"))):
        assert e.expand(Seed(p, e.model_id), 0) == []


# --- seed integrity: corruption must be caught, not expanded ---

def test_single_bit_flip_rejected_everywhere_in_the_packet():
    s = seed_from_message(b"integrity", "test-model", epoch=11)
    wire = s.to_wire()
    for i in range(len(wire)):
        for bit in (0x01, 0x80):
            bad = bytearray(wire)
            bad[i] ^= bit
            try:
                Seed.from_wire(bytes(bad))
                assert False, f"byte {i} bit {bit:#x} flipped and still accepted"
            except ValueError:
                pass  # CRC mismatch, bad length, or bad utf-8 — all loud


def test_truncated_wire_rejected():
    wire = seed_from_message(b"x", "m").to_wire()
    for cut in range(1, len(wire)):
        try:
            Seed.from_wire(wire[:cut])
            assert False, f"accepted a packet truncated to {cut} bytes"
        except ValueError:
            pass


def test_clean_wire_still_accepted():
    """Guard against the above passing because from_wire rejects
    everything."""
    s = seed_from_message(b"integrity", "test-model", epoch=11)
    assert Seed.from_wire(s.to_wire()) == s


# --- error handling: unsupported model_id must be loud if asked ---

def test_expand_strict_rejects_foreign_model_id():
    orb = OrbitalExpander()
    geo = GeomagneticExpander(FieldModel(0.0, 0.0, 5e4, "a"))
    s = seed_from_message(b"x", geo.model_id)
    try:
        orb.expand_strict(s, 4)
        assert False, "should have raised ModelMismatch"
    except ModelMismatch as e:
        assert geo.model_id in str(e) and orb.model_id in str(e)


def test_expand_strict_passes_matching_model_id():
    orb = OrbitalExpander()
    s = seed_from_message(b"x", orb.model_id)
    assert orb.expand_strict(s, 4) == orb.expand(s, 4)


def test_expand_stays_permissive_for_the_gate_demo():
    """expand() must NOT check model_id — demo_failures.py depends on
    showing what a mismatch actually produces."""
    orb = OrbitalExpander()
    geo = GeomagneticExpander(FieldModel(0.0, 0.0, 5e4, "a"))
    s = seed_from_message(b"x", geo.model_id)
    assert len(orb.expand(s, 4)) == 4


def test_matching_model_id_does_not_imply_matching_params():
    """The limit of the model_id check, asserted so nobody mistakes it
    for authentication: same id, different survey, silent divergence."""
    a = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "here"))
    b = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "there"))
    s = seed_from_message(b"x", a.model_id, epoch=4)
    assert a.model_id == b.model_id
    assert b.accepts(s)
    assert a.expand(s, 16) != b.expand(s, 16)


# --- the Expander contract is enforced, not merely documented ---

def test_expander_is_abstract():
    try:
        Expander()
        assert False, "Expander should not be instantiable"
    except TypeError:
        pass


def test_incomplete_expander_is_rejected():
    class NoExpand(Expander):
        model_id = "broken.v1"
    try:
        NoExpand()
        assert False, "subclass without expand() should not be instantiable"
    except TypeError:
        pass


def test_template_expander_satisfies_the_contract():
    t = TemplateExpander(TemplateModel(1.5, "anchor"))
    s = seed_from_message(b"x", t.model_id, epoch=5)
    assert t.expand(s, 16) == t.expand(s, 16)
    assert t.accepts(s)
    assert len(t.keystream(s, 32)) == 32


def test_template_model_key_is_unambiguous():
    """The mistake this repo made twice (F-02, F-03) must not be in the
    file people copy."""
    assert TemplateModel(1.0, "abc").key() != TemplateModel(1.0, "ab").key()


# --- F-13: what the shared model actually regenerates ---

def test_regime_a_codebook_recovers_the_message():
    geo = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "anchor"))
    book = [b"hold", b"fall back", b"meet at the north cache", b"abort"]
    msg = book[2]
    s = seed_from_message(msg, geo.model_id, epoch=42)
    assert codebook_recover(s, book, geo.model_id, 42) == msg
    # 15-byte payload regenerated a longer message: this regime compresses
    assert len(s.payload) < len(msg)


def test_regime_a_fails_without_the_shared_message_space():
    geo = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "anchor"))
    s = seed_from_message(b"not in the book", geo.model_id, epoch=42)
    assert codebook_recover(s, [b"hold", b"abort"], geo.model_id, 42) is None


def test_regime_a_is_bound_to_model_id_and_epoch():
    geo = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "anchor"))
    book = [b"hold", b"abort"]
    s = seed_from_message(b"abort", geo.model_id, epoch=42)
    assert codebook_recover(s, book, geo.model_id, 43) is None
    assert codebook_recover(s, book, "other.model.v1", 42) is None


def test_regime_b_pad_roundtrips_an_arbitrary_message():
    geo = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "anchor"))
    msg = b"a message that is in no codebook anywhere, 0x%$ bytes and all"
    s = seed_from_message(msg, geo.model_id, epoch=7)
    ct = pad_apply(geo, s, msg)
    assert ct != msg
    assert pad_apply(geo, s, ct) == msg
    # and it does NOT compress: ciphertext is message-sized
    assert len(ct) == len(msg)


def test_regime_b_gate_holds_against_wrong_field_model():
    right = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "here"))
    wrong = GeomagneticExpander(FieldModel(0.0, 0.0, 50000.0, "elsewhere"))
    msg = b"meet at the north cache before the field flips"
    s = seed_from_message(msg, right.model_id, epoch=7)
    ct = pad_apply(right, s, msg)
    assert pad_apply(wrong, s, ct) != msg


def test_expansion_is_not_invertible_to_the_message():
    """The literal reading of the core invariant, pinned as false so the
    README and the code cannot drift apart again. (F-13.)"""
    geo = GeomagneticExpander(FieldModel(-1.6, 74.8, 57200.0, "anchor"))
    msg = b"meet at the north cache"
    s = seed_from_message(msg, geo.model_id, epoch=42)
    sched = geo.expand(s, len(msg))
    assert all(isinstance(v, float) for v in sched)
    assert bytes(int((v + 1.0) * 127.5) & 0xFF for v in sched) != msg


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
