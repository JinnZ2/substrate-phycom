# REVIEW.md

| Section | Findings |
|---|---|
| 1. Inconsistencies | 4 |
| 2. Markdown Information Gaps | 5 |
| 3. Code Audit | 12 |
| 4. Organizational Structure | 5 |
| 5. Limitations Mitigation | 5 items × 5 sub-items = 25 assessments |
| 6. Discoverability & Crawler Optimization | 9 |

---

### 1. Inconsistencies

**1.1 — epoch range: `Seed` constructor vs `seed_from_message` vs `to_wire`**
- `Seed.__post_init__` now enforces `epoch ∈ [0, 0xFFFF]` (`core/seed.py`).
- `to_wire` packs epoch as `!H` (2 bytes, unsigned) — consistent.
- `seed_from_message` packs epoch as `!I` (4 bytes) in the hash input — inconsistent width. The hash input uses 32-bit epoch while the wire uses 16-bit. For `epoch ∈ [0, 65535]` the numerical value is the same; the width difference is inconsequential in practice but is a latent inconsistency if the hash width is ever widened.
  - **Fix:** Use `struct.pack("!H", epoch)` in `seed_from_message` to match wire width exactly, or document the deliberate 32-bit choice.

**1.2 — `FOLD_FLAT` and `FOLD_SAFE` produce different seeds for the same inputs**
- `seed_from_message(b"hello", "geomag.field.v1", epoch=7)` returns a different `payload` depending on `fold`. The wire-roundtrip test (`test_seed_wire_roundtrip`) uses `FOLD_SAFE` (the new default). Any caller using `FOLD_FLAT` (the original behaviour) will derive a seed that the other side can't reproduce if it uses `FOLD_SAFE`.
- **Fix:** Document the fold mode as part of the shared out-of-band agreement between endpoints, alongside the `model_id` and field parameters.

**1.3 — `OrbitalExpander` defaults changed between original and audited code**
- Original: `entropy=ENTROPY_PARTIAL` (implicit), `t_mode=T_NORMALIZED`.
- Audited: `entropy=ENTROPY_FULL` (new default), `t_mode=T_NORMALIZED`.
- A seed created with the original code and expanded with the new default `OrbitalExpander` produces a different schedule. The `model_id` (`"orbital.kepler.v1"`) has not changed, so the gate does not catch this mismatch.
- **Fix:** Either version the model_id (e.g., `"orbital.kepler.v2"`) when the entropy mode changes, or require `entropy` to be passed explicitly (no default) to force the caller to make an intentional choice.

**1.4 — `FieldModel` `key_version` is not part of the wire format or model_id**
- Two `GeomagneticExpander` instances with the same `FieldModel` parameters but different `key_version` values derive different HMAC keys and expand the same seed to different (incompatible) schedules. Nothing in the seed or wire format encodes which key_version was used.
- **Fix:** Either encode `key_version` in the `model_id` string (e.g., `"geomag.field.v1.kv2"`) or document it as a required out-of-band configuration item alongside the field parameters.

---

### 2. Markdown Information Gaps

**2.1 — README.md is a stub**
- Current content: "# substrate-phycom\nConnective tissue". Provides no orientation for a new reader, no usage instructions, no context for the four-repo stack.
- **Intent:** Describe the physics-as-decompressor principle, the role of this repo as the pluggable-expander seam, and link to the three sibling repos.
- **Fix:** Expand README with the content already present in CLAUDE.md (layout, house rules, run commands). README is what crawlers and humans read first; CLAUDE.md is internal tooling guidance.

**2.2 — CLAUDE.md does not document the multi-choice constants**
- After the audit, several mode constants were added (`FOLD_FLAT`/`FOLD_SAFE`, `KEY_V1`/`KEY_V2`, `T_NORMALIZED`/`T_ABSOLUTE`, `ENTROPY_PARTIAL`/`ENTROPY_FULL`, `KEYSTREAM_ABS_MOD`/`KEYSTREAM_SIGNED`). CLAUDE.md's Layout section still describes the original single-path behaviour.
- **Fix:** Add a "Design choices" section to CLAUDE.md listing each constant pair, its default, and the one-line tradeoff.

**2.3 — No documentation on out-of-band agreement requirements**
- The gate property depends on both endpoints agreeing on: `model_id`, `FieldModel` parameters, `key_version`, `fold` mode used in `seed_from_message`, and `entropy`/`t_mode` for orbital. None of these are transmitted on the wire. There is no document describing what constitutes the "shared out-of-band context" that must match.
- **Fix:** Add a `PROTOCOL.md` or a section in README: "What both endpoints must agree on before any seed is exchanged."

**2.4 — No documentation on the `epoch` rollover strategy**
- `WIRE_EPOCH_MAX = 0xFFFF = 65535`. At a day-index cadence this is 179 years. At an hour-index cadence it rolls over in 7.5 years. There is no documentation advising callers which time unit to use or how to handle rollover.
- **Fix:** Add one paragraph in CLAUDE.md or README: "epoch is a 16-bit day/hour/slot index. Parties must agree on the time base. Rollover at 65535 → 0 is valid; both ends must be aware."

**2.5 — `REVIEW.md` (this file) will become stale**
- This review reflects the state of the codebase at a single point in time. As files are added and the protocol matures, the findings here will diverge from reality.
- **Fix:** Date-stamp this file and treat it as a snapshot, not living documentation. Move actionable items to GitHub Issues.

---

### 3. Code Audit

Findings are ordered by severity. All critical findings from the independent math audit have been addressed in the committed code; they are listed here for completeness with their resolution status.

**3.1 [FIXED] — `seed.py`: epoch silently truncated on wire; round-trip lossy for `epoch > 65535`**
- `to_wire()` packed `epoch & 0xFFFF`; `from_wire()` restored only 16 bits. Seeds with `epoch > 65535` round-tripped to a different integer, producing a different expansion.
- **Resolution:** `Seed.__post_init__` now enforces `0 ≤ epoch ≤ WIRE_EPOCH_MAX`. Construction with out-of-range epoch raises `ValueError`.

**3.2 [FIXED] — `seed.py`: `seed_from_message` hash input ambiguous**
- `message + model_id.encode() + pack(epoch)` — different `(message, model_id)` pairs sharing a boundary produced identical payloads.
- **Resolution:** `FOLD_SAFE` (default) prepends `pack(len(message))`. `FOLD_FLAT` retained as legacy option.

**3.3 [FIXED] — `geomagnetic.py`: `FieldModel.key()` collision on `anchor`/`lattice_hash` boundary**
- `anchor.encode() + lattice_hash.encode()` without delimiter. `("abc","")` == `("ab","c")`.
- **Resolution:** `KEY_V2` (default) prepends `pack(len(anchor_bytes))`. `KEY_V1` retained as legacy.

**3.4 [FIXED] — `orbital.py`: `steps` changed schedule shape, not just resolution**
- `t = (k + epoch) / steps` — `expand(seed, 10)[:3] != expand(seed, 3)`.
- **Resolution:** `T_ABSOLUTE` mode uses `t = (k + epoch) / sample_rate` (fixed time grid). `T_NORMALIZED` retained as default for backward compatibility.

**3.5 [FIXED] — `orbital.py`: 80% of seed entropy unused**
- Only `payload[0:len(periods)]` (3 bytes with default periods) influenced phase. Effective key space: 24 bits.
- **Resolution:** `ENTROPY_FULL` (default) derives each channel's phase from `SHA-256(payload + pack(ci))`. `ENTROPY_PARTIAL` retained as legacy.

**3.6 [FIXED] — `seed.py`: `from_wire()` raised `struct.error` on short input**
- Inputs shorter than 21 bytes caused `struct.unpack` to raise `struct.error` instead of `ValueError`.
- **Resolution:** Minimum-length check at entry: raises `ValueError` with a message for `len(data) < MIN_WIRE_BYTES`.

**3.7 [FIXED] — `seed.py`: negative `epoch` — three inconsistent behaviours**
- Constructor: accepted. `to_wire`: silently wrapped (`-1 → 65535`). `seed_from_message`: raised `struct.error`.
- **Resolution:** Constructor now rejects `epoch < 0` with `ValueError`.

**3.8 [FIXED] — `expander.py`: `abs()` in `keystream()` discards sign**
- `int(abs(v) * 1e6) & 0xFF` — `v` and `-v` mapped to the same byte.
- **Resolution:** `KEYSTREAM_SIGNED` (default) uses `int((v + 1.0) * 127.5) & 0xFF`. `KEYSTREAM_ABS_MOD` retained as legacy.

**3.9 [FIXED] — `geomagnetic.py`: `lattice_hash_from_axes` lost vector structure**
- `[[a, b]]` and `[[a], [b]]` produced identical digests.
- **Resolution:** `version=2` (default) prepends `pack(len(vec))` per vector.

**3.10 [REMAINING] — `orbital.py`: `t_mode=T_NORMALIZED` large-epoch window drift**
- In `T_NORMALIZED` mode, large `epoch` values shift the window start unboundedly. The sinusoidal output is numerically valid but the "normalized" framing is misleading for large epochs.
- **Recommendation:** If epochs > ~1000 are expected, use `T_ABSOLUTE`. Document as a usage note in `OrbitalExpander.__init__`.

**3.11 [REMAINING] — `orbital.py`: `t` never reaches 1.0 in `T_NORMALIZED` mode**
- Half-open interval `[0, (steps-1)/steps)` — correct DFT convention but undocumented. No finite `steps` covers a complete period of the slowest oscillator.
- **Recommendation:** Add a one-line docstring note: "Uses half-open interval; no finite steps covers a full oscillator period (DFT convention)."

**3.12 [REMAINING] — `expander.py`: `keystream()` `KEYSTREAM_SIGNED` range edge**
- `int((v + 1.0) * 127.5) & 0xFF`: for `v = -1.0` yields `int(0.0) = 0`; for `v = +1.0` yields `int(255.0) = 255`. The mapping is `[0, 255]` inclusive, which is correct. However for the geomagnetic expander, `v = +1.0` only occurs when `word = 65535` and `v = -1.0` only when `word = 0` — both are HMAC outputs and statistically rare. In practice the range is `[1, 254]` with high probability. Not a bug; worth noting if byte value `0` or `255` has semantic meaning in a downstream protocol.

---

### 4. Organizational Structure Suggestions

**4.1 — Add `__init__.py` exports for public API**
- Currently `core/__init__.py` and `expanders/__init__.py` are empty. Downstream code must know to import from `core.seed`, `core.expander`, etc.
- **Recommendation:** Export the primary symbols from package `__init__.py`:
  ```python
  # core/__init__.py
  from core.seed import Seed, seed_from_message, FOLD_SAFE, FOLD_FLAT
  from core.expander import Expander, KEYSTREAM_SIGNED, KEYSTREAM_ABS_MOD
  ```
  This lets callers write `from core import Seed` instead of `from core.seed import Seed`.

**4.2 — `tests/` should be a package or use a test runner**
- Currently tests are run with `python tests/test_stack.py`. This works but doesn't scale when multiple test files exist.
- **Recommendation:** Keep the `__main__` runner for phone-compatibility, but also make tests discoverable by `python -m pytest tests/` for CI. No pytest dependency is needed in production — add it only in a `requirements-dev.txt`.

**4.3 — Separate `expanders/registry.py` for model_id → class mapping**
- Currently there is no mechanism to look up an expander by `model_id`. The demo hardcodes `OrbitalExpander()` and `GeomagneticExpander(field)`. When a received seed's `model_id` is unknown, there is no dispatch path.
- **Recommendation:** Add `expanders/registry.py`:
  ```python
  _REGISTRY = {}
  def register(cls): _REGISTRY[cls.model_id] = cls; return cls
  def get(model_id): return _REGISTRY.get(model_id)
  ```
  Decorate each expander class with `@register`.

**4.4 — `integration/demo.py` hardcodes field values**
- The demo hardcodes northern MN field parameters. A reader cannot tell which values are real WMM values and which are illustrative.
- **Recommendation:** Move demo parameters to a `integration/demo_config.py` or a top-of-file `DEMO_FIELD` constant with a comment marking it as illustrative.

**4.5 — No `Makefile` or `pyproject.toml`**
- The only way to know how to run the project is `CLAUDE.md`. For external contributors or CI, a minimal `Makefile` with `make test` and `make demo` targets costs one file and removes all ambiguity.

---

### 5. Limitations Mitigation Checklist

*(Applied as: is this codebase, as a physics-grounding / shared-model communication system, robust against the listed limitations?)*

**5.1 Symbolic–Subsymbolic Gap**

| Sub-item | Status | Recommendation |
|---|---|---|
| Explicit logical-form extraction | **Missing** | The `Expander` contract is purely numeric (floats). No symbolic representation of the physics model is extracted or verified. | 
| Connection to symbolic solvers | **Missing** | No formal verification that a given `FieldModel` or `OrbitalExpander` config is physically realizable. |

*Recommendation:* Add a `validate()` method to `Expander` that checks model parameters against known physical bounds (e.g., declination ∈ [-180°, 180°], inclination ∈ [-90°, 90°], intensity > 0 nT). This is not a solver, but it is a symbolic boundary check.

**5.2 Grounding Problem**

| Sub-item | Status | Recommendation |
|---|---|---|
| Units/dimensions checked | **Partially addressed** | Parameter names carry units (`_deg`, `_nt`) but no runtime unit validation exists. |
| Lower-layer constraints enforced | **Addressed** | `Seed.__post_init__` validates payload length and epoch range. `FieldModel.key()` validates nothing. |
| Meta-grounding flag for revolutionary claims | **Missing** | No runtime check that the `expand()` output has the statistical properties (entropy, distribution) required for the gate to function. |

*Recommendation:* Add `FieldModel.validate()` that rejects clearly non-physical values (intensity = 0, declination > 360, etc.). Add a `GeomagneticExpander.self_test(seed)` that verifies the expansion is non-trivial (non-zero variance over 64 steps).

**5.3 Semantic Ambiguity**

| Sub-item | Status | Recommendation |
|---|---|---|
| Vague terms quantified | **Partially addressed** | "noise" in the gate context is undefined. The gate test only checks `!=`, not that the wrong expansion is statistically independent. |
| Scope explicit | **Addressed** | `epoch`, `model_id`, and `anchor` together define the temporal/spatial scope. |
| Reference class specified | **Partially addressed** | `model_id` names the reference class, but there is no registry mapping `model_id` to a validated implementation. |

*Recommendation:* Add a `GeomagneticExpander.gate_distance(seed, other_expander, steps=64)` that computes the mean absolute difference between two expansions. A value near 0 indicates same model; a value near 0.5 (expected for HMAC noise) confirms the gate is working. Add a test asserting this value exceeds a threshold.

**5.4 Falsifiability Paradox**

| Sub-item | Status | Recommendation |
|---|---|---|
| Refutation-observation set enumerable | **Missing** | No mechanism to enumerate what observations would falsify a given expansion. |
| Escape-hatch detector | **Missing** | No check for degenerate expansions (constant output, zero variance) that would satisfy `==` vacuously. |
| Falsifiable/unfalsifiable classifier | **Missing** | Not applicable at the code level, but the gate test only checks inequality, not statistical independence. |

*Recommendation:* The most practical step is a variance check in `expand()` output. If `max(out) - min(out) < 0.01`, the expansion is suspiciously flat and should raise a warning.

**5.5 Formal Verification vs. Complexity**

| Sub-item | Status | Recommendation |
|---|---|---|
| Formal proof scoped | **Missing** | No formal proof that the CRC, HMAC, or SHA-256 usage meets any security or integrity standard. |
| Background knowledge accessible | **Addressed** | The docstrings reference CRC-16/CCITT-FALSE, HMAC-SHA-256, and IGRF/WMM by name, linking to external knowledge. |
| Probabilistic fallback with confidence | **Missing** | No confidence score or error probability is surfaced to the caller. |

*Recommendation:* For the CRC: document the BER (bit error rate) at which the 16-bit CRC has a detectable miss probability of 1/65536 — one line in the `_crc16` docstring. For the gate: document the probability that two random `FieldModel` instances produce the same HMAC key (negligible given SHA-256, but worth stating).

---

### 6. Discoverability & Crawler Optimization

**6.1 — README.md lacks a "What is this?" summary**
- Missing. Current README has only a title and "Connective tissue".
- **Ready-to-paste:**
  ```markdown
  ## What is this?

  substrate-phycom is a physics-as-decompressor communication library.
  Instead of transmitting a message, you transmit a **seed** (15 bytes).
  A shared physics model on both ends regenerates the full message.
  The model never crosses the wire — it is both the compression and the
  access gate. No shared model, no message.

  Part of a four-repo stack: [geometric-to-binary](https://github.com/JinnZ2/Geometric-to-Binary-Computational-Bridge) · [BE2-communication](https://github.com/JinnZ2/BE2-communication) · [orbital-phycom](https://github.com/JinnZ2/orbital-phycom) · **substrate-phycom** (this repo).
  ```

**6.2 — No repository topics / tags**
- GitHub topics are not visible in the repo content but should be set in repo settings.
- **Recommended topics:** `physics`, `compression`, `geomagnetic`, `communication`, `seed`, `deterministic`, `off-grid`, `lora`, `ham-radio`, `cc0`, `stdlib`, `python`

**6.3 — No `KEYWORDS.md` or `KEYWORDS.txt`**
- **Ready-to-paste (`KEYWORDS.md`):**
  ```markdown
  # Keywords

  physics-as-decompressor, seed-based communication, geomagnetic field model,
  orbital mechanics compression, deterministic keystream, transport-agnostic,
  off-grid communication, LoRa, HAM radio, CB radio, shared model gate,
  IGRF, WMM, crystal navigation, lattice hash, BE2, orbital-phycom,
  geometric-to-binary, stdlib, phone-buildable, CC0
  ```

**6.4 — No `CITATION.cff`**
- **Ready-to-paste (`CITATION.cff`):**
  ```yaml
  cff-version: 1.2.0
  message: "This software is CC0. No citation required, but attribution is welcome."
  title: "substrate-phycom"
  abstract: >
    Physics-as-decompressor, carrier-agnostic communication stack.
    Transmit a seed; a shared physics model regenerates the message.
  license: CC0-1.0
  repository-code: https://github.com/JinnZ2/substrate-phycom
  keywords:
    - physics-as-decompressor
    - geomagnetic
    - orbital mechanics
    - deterministic communication
    - off-grid
  ```

**6.5 — No "Why This Matters" urgency statement**
- **Ready-to-paste (add to README after the summary):**
  ```markdown
  ## Why this matters

  Bandwidth monopolies derive their value from the assumption that you
  need their pipe. Move the decompressor into the shared physics model
  and the pipe becomes a commodity — CB, HAM, LoRa, a knock on a length
  of pipe. Any carrier that can move 15 bytes can move any message.
  ```

**6.6 — No structured metadata (JSON-LD or YAML frontmatter)**
- Most useful in a GitHub Pages or documentation site. For now, the `CITATION.cff` (6.4) covers the machine-readable metadata need.

**6.7 — No public API import example in README**
- **Ready-to-paste:**
  ```markdown
  ## Quick start

  ```python
  from core.seed import seed_from_message
  from expanders.geomagnetic import GeomagneticExpander, FieldModel

  field = FieldModel(declination_deg=-1.6, inclination_deg=74.8,
                     intensity_nt=57200.0, anchor="my-place")
  expander = GeomagneticExpander(field)
  seed = seed_from_message(b"your message here", model_id=expander.model_id, epoch=0)
  schedule = expander.expand(seed, steps=64)
  ```
  ```bash
  PYTHONPATH=. python -m integration.demo   # full stack demo
  PYTHONPATH=. python tests/test_stack.py   # 22 tests, no test framework needed
  ```
  ```

**6.8 — License clearly marked**
- LICENSE file exists and is CC0 1.0 Universal. ✓
- README does not mention the license.
- **Ready-to-paste (add to README footer):**
  ```markdown
  ## License

  CC0 1.0 Universal — public domain. No rights reserved.
  ```

**6.9 — No issue templates for anonymous feedback**
- **Ready-to-paste (`.github/ISSUE_TEMPLATE/feedback.md`):**
  ```markdown
  ---
  name: Feedback / Question
  about: Question, observation, or use case
  ---
  **What are you trying to do?**

  **What did you expect?**

  **What happened instead?**
  ```
