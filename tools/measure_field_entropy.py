#!/usr/bin/env python3
"""
measure_field_entropy.py — how much key material is really in a FieldModel?

    python tools/measure_field_entropy.py [lat] [lon]

expanders/geomagnetic.py is written as though the geomagnetic field at a
place is the shared secret. This measures that claim instead of assuming
it, and the answer is that the physics is a SALT, not a key. (NOTEBOOK.md
F-17.)

Why the obvious estimate is wrong: declination, inclination and intensity
look like three independent parameters, so multiplying their ranges gives
a comfortable-looking number. They are not independent. All three are
functions of position, so the triple lies on a 2-dimensional manifold
embedded in 3-space, and the key space is bounded by the number of
distinguishable POSITIONS — not by the product of three ranges. Section 1
measures the size of that error directly.

Model: centred tilted dipole, stdlib math only, no data files. It is not
IGRF and does not need to be — what is being measured is the correlation
structure, which any dipole-dominated model reproduces. The real field
adds crustal anomalies on top, which raise the count locally; see the
limits printed at the end.
"""

from __future__ import annotations

import math
import sys

# IGRF-2020-ish geomagnetic north pole; equatorial surface intensity
POLE_LAT, POLE_LON = 80.65, -72.68
B_EQ_NT = 30000.0
R_EARTH_KM = 6371.0
LAND_KM2 = 1.489e8

# key() derivations/sec: SHA-256 over ~40 bytes, one ordinary core.
# Deliberately conservative — a GPU is several orders of magnitude faster.
RATE = 5e6


def dipole_field(lat, lon):
    """(declination_deg, inclination_deg, intensity_nt) at a point."""
    p, l = math.radians(lat), math.radians(lon)
    pb, lb = math.radians(POLE_LAT), math.radians(POLE_LON)
    dl = lb - l
    cos_tm = math.sin(p) * math.sin(pb) + math.cos(p) * math.cos(pb) * math.cos(dl)
    cos_tm = max(-1.0, min(1.0, cos_tm))
    tm = math.acos(cos_tm)
    # horizontal field points at the geomagnetic pole; declination is the
    # great-circle azimuth from the point to that pole
    y = math.sin(dl) * math.cos(pb)
    x = math.cos(p) * math.sin(pb) - math.sin(p) * math.cos(pb) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)),
            math.degrees(math.atan2(2.0 * math.cos(tm), math.sin(tm))),
            B_EQ_NT * math.sqrt(1.0 + 3.0 * cos_tm * cos_tm))


def rounded(lat, lon):
    """Exactly what FieldModel.key() hashes: round(d,3), round(i,3), round(nt,1)."""
    d, i, nt = dipole_field(lat, lon)
    return (round(d, 3), round(i, 3), round(nt, 1))


def km_per_deg_lon(lat):
    return 111.32 * math.cos(math.radians(lat))


def bits(n):
    return math.log2(n) if n > 0 else 0.0


def grid(lat0, lon0, span_km, n):
    dlat, dlon = span_km / 111.32, span_km / km_per_deg_lon(lat0)
    keys, ds, is_, nts = set(), set(), set(), set()
    for a in range(n):
        for b in range(n):
            k = rounded(lat0 - dlat / 2 + dlat * a / (n - 1),
                        lon0 - dlon / 2 + dlon * b / (n - 1))
            keys.add(k); ds.add(k[0]); is_.add(k[1]); nts.add(k[2])
    return keys, ds, is_, nts


def resolution_m(lat0, lon0, axis):
    """Metres you must move along `axis` before the rounded triple changes."""
    k0, lo, hi = rounded(lat0, lon0), 0.0, 50.0
    for _ in range(60):
        mid = (lo + hi) / 2
        probe = (rounded(lat0 + mid / 111.32, lon0) if axis == "north"
                 else rounded(lat0, lon0 + mid / km_per_deg_lon(lat0)))
        lo, hi = (mid, hi) if probe == k0 else (lo, mid)
    return hi * 1000


def main(lat0=47.9, lon0=-91.5):
    print("=" * 74)
    print("FieldModel key space, measured")
    print("=" * 74)
    print(f"site      : {lat0}N {lon0}E     model: centred tilted dipole")
    print("rounding  : as FieldModel.key() uses — decl 1e-3, incl 1e-3, F 0.1 nT")
    print()

    print("--- 1. are the three parameters independent? (no) ---")
    print(f"{'region':>16} {'joint distinct':>15} {'bits':>6} "
          f"{'if independent':>15} {'bits':>6} {'overcount':>12}")
    for span in (1, 10):
        keys, ds, is_, nts = grid(lat0, lon0, span, 180)
        naive = len(ds) * len(is_) * len(nts)
        print(f"{f'{span}x{span} km':>16} {len(keys):>15,} {bits(len(keys)):>6.1f} "
              f"{naive:>15,} {bits(naive):>6.1f} {naive/len(keys):>11.0f}x")
    print("  Multiplying the three ranges counts a 3-D box around a 2-D surface.")
    print()

    print("--- 2. key density (grid halved until the count converges) ---")
    prev, density = None, 0.0
    for n in (130, 260, 520, 900):
        keys, *_ = grid(lat0, lon0, 2.0, n)
        density = len(keys) / 4.0
        sp = 2000 / (n - 1)
        limited = " GRID-LIMITED" if len(keys) == n * n else ""
        d = "" if prev is None else f"  ({(density/prev-1)*100:+.1f}%)"
        print(f"  {n}x{n}, {sp:5.1f} m spacing -> {density:9.1f} keys/km^2{d}{limited}")
        prev = density
    cell = 1e6 / density
    print(f"\n  converged: {density:,.0f} keys/km^2 = one per {cell:,.0f} m^2 "
          f"(~{math.sqrt(cell):.0f} m square)")
    print(f"  moving north, the key changes after {resolution_m(lat0, lon0, 'north'):.1f} m")
    print(f"  moving east,  the key changes after {resolution_m(lat0, lon0, 'east'):.1f} m")
    print()

    print("--- 3. what an attacker searches, by how well they know your location ---")
    print(f"{'attacker knows position to':>32} {'candidates':>18} {'bits':>7} {'to exhaust':>12}")
    for span, human in ((0.1, "100 m (a building)"),
                        (1, "1 km (a town block)"),
                        (10, "10 km (a small town)"),
                        (100, "100 km (a county)"),
                        (1000, "1000 km (a region)")):
        n = density * span * span
        s = n / RATE
        t = (f"{s*1000:.2f} ms" if s < 1 else f"{s:.1f} s" if s < 3600
             else f"{s/3600:.1f} h" if s < 86400 else f"{s/86400:.1f} d")
        print(f"{human:>32} {n:>18,.0f} {bits(n):>7.1f} {t:>12}")
    print()

    print("--- 4. ceiling: attacker knows nothing about where you are ---")
    for label, a in (("land surface", LAND_KM2),
                     ("whole Earth", 4 * math.pi * R_EARTH_KM ** 2)):
        n = density * a
        print(f"  {label:>13}: {n:>18,.0f} = {bits(n):>4.1f} bits "
              f"({n/RATE/86400:.2f} core-days)")
    print()

    print("--- verdict ---")
    print(f"  HMAC-SHA256 key space ................. 2^256")
    print(f"  seed payload .......................... 2^120")
    print(f"  smooth field, global ceiling .......... 2^{bits(density*LAND_KM2):.0f}")
    print(f"  smooth field, county-level guess ...... 2^{bits(density*1e4):.0f}")
    print()
    print("  The field is a SALT — it makes the search per-place, which is")
    print("  worth something. It is not a key. Any real strength lives in")
    print("  `anchor` and `lattice_hash`, which are strings, not physics.")
    print("  Treat a FieldModel with a guessable anchor and an empty")
    print("  lattice_hash as UNKEYED.")
    print()
    print("--- limits of this measurement ---")
    print("  * Dipole model: the real field adds crustal anomalies, which")
    print("    raise the local count. They do not change the shape of the")
    print("    argument — anomaly structure is exactly what lattice_hash is")
    print("    for, and it is surveyed data, not published geophysics.")
    print("  * Assumes the attacker knows the rounding and the key layout.")
    print("    They do: this repo is CC0.")
    print("  * Ignores secular variation. Including it would ADD a time")
    print("    dimension the attacker must also search — worth measuring,")
    print("    and it is bounded by how stale your survey is allowed to be.")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(float(a[0]), float(a[1])) if len(a) == 2 else main()
