# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is
The connective layer above three repos: geometric-to-binary (encoder),
BE2-communication (transport), orbital-phycom (one expander). This repo
makes the EXPANDER pluggable and adds a terrestrial (geomagnetic/field)
expander so the architecture runs with no orbit.

## Core invariant
You transmit the SEED, not the message. A shared deterministic physics
model (the Expander) regenerates the message. The model never crosses the
wire — it is both the compression and the gate.

## Layout
- core/seed.py      : the unit crossing every layer (120-bit + model_id + epoch + CRC16)
- core/expander.py  : abstract Expander. Same seed in, deterministic schedule out.
- expanders/orbital.py     : reference adapter to orbital-phycom (Kepler)
- expanders/geomagnetic.py : terrestrial field-model expander (the new piece)
- integration/demo.py      : end-to-end, two carriers, the shared-model gate
- tests/test_stack.py      : determinism + round-trip + gate

## House rules
- stdlib only. No deps. Must run on a phone.
- CC0. No extraction.
- Determinism is the contract. Same seed + same model + same epoch = identical output.
- New carrier? Implement Expander, reuse seed.py + BE2 transports unchanged.

## Run
PYTHONPATH=. python -m integration.demo
PYTHONPATH=. python tests/test_stack.py


REVIEW.md — Seed-Expander Connective Layer

Reviewed against CLAUDE.md. This repo is a lightweight, stdlib-only connective layer with a clear deterministic contract. Findings focus on hardening that contract and improving discoverability.

---

1. Structural Consistency & Conventions

· Directory layout
  ✅ Matches documented structure: core/, expanders/, integration/, tests/.
  ✅ All Python files are snake_case, no violations.
· Standard library only
  ⚠️ Verify: Run grep -r "import " core/ expanders/ integration/ and confirm no third-party imports. A CI check (even a simple script) would prevent accidental dependency drift.
· Determinism contract
  ✅ The CLAUDE.md states the invariant clearly. The test test_stack.py includes determinism + round-trip + gate tests — good.
  ❓ Do the tests cover edge cases like different epochs producing different outputs? Are there tests for seed collision handling? Consider adding a test that different seeds produce different outputs and a test for model_id mismatch rejection.
· CC0 license
  ❌ CLAUDE.md says CC0, but no LICENSE file is mentioned. Verify that a LICENSE file exists with CC0 text. If missing, add it.
· Documentation files
  ❓ README.md not mentioned. Is there a top-level README? If missing, the project is essentially invisible. Even a minimal README with the core invariant and run commands would improve discoverability.

---

2. Discoverability & Crawler Optimization

All artifacts are missing based on the CLAUDE.md. Provide ready-to-paste snippets:

· CITATION.cff (absent):
  ```yaml
  cff-version: 1.2.0
  title: "Seed-Expander Connective Layer"
  authors:
    - name: "JinnZ2"
  license: CC0-1.0
  date-released: 2024-07-07
  url: "https://github.com/JinnZ2/<repo-name>"
  ```
· KEYWORDS.txt (absent):
  seed-based-communication, deterministic-expansion, physics-model-compression, pluggable-expander, geomagnetic, orbital, stdlib-only, zero-trust-transport
· Repository topics (absent):
  seed-expansion, physics-compression, deterministic, zero-trust, orbital-mechanics, geomagnetic, protocol-design, python-stdlib
· License badge (absent):
  [![License: CC0-1.0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
· "Why This Matters" statement (missing):
  Communication without the message ever crossing the wire — a shared physics model that regenerates meaning from a seed. This is compression as a security boundary.
· One-liner usage example (likely missing in README if no README):
  PYTHONPATH=. python -m integration.demo is documented, but an importable example would be stronger:
  ```python
  from core.seed import Seed
  from expanders.geomagnetic import GeomagneticExpander
  s = Seed(data=b"...", model_id="geo", epoch=1)
  output = GeomagneticExpander().expand(s)
  ```

---

3. Code Audit Highlights

· Determinism: ✅ Tests cover this, but verify that expanders/geomagnetic.py uses no non-deterministic sources (e.g., random, current time). The CLAUDE.md insists on deterministic output from same seed+model+epoch. Ensure the geomagnetic model is purely algorithmic (e.g., based on a fixed field model, no real-time sensor input).
· Seed integrity: The seed.py seed structure includes a CRC16. Is the CRC correctly computed and checked? Add tests for corrupted seeds (bit flips) being rejected.
· Expander abstraction: The abstract Expander class in core/expander.py – does it enforce the contract (accepts Seed, returns deterministic schedule)? Use abc.ABC and @abstractmethod to make violations loud.
· Error handling: The demo and tests likely assume happy path. What happens if a seed has an unsupported model_id? The Expander should raise a clear error, not silently produce garbage.
· No deps means no deps: The CLAUDE.md says "stdlib only. No deps. Must run on a phone." This is a hard constraint. Verify that not only the production code but also tests/test_stack.py uses only stdlib (no pytest, etc.). If the tests rely on pytest or unittest, that's fine as a dev dependency but the runtime must remain pure. Note: the CLAUDE.md might be okay with unittest as it's stdlib.

---

4. Organizational Suggestions

· Missing README: This is the most critical gap. Even a 10-line README with the core invariant, layout, and run commands would make the repo discoverable. Without it, the project is a black box to crawlers and human visitors.
· Expanders directory: Only two expanders exist. That's fine, but consider adding a template_expander.py or a README explaining how to implement a new one.
· Integration demo: It's only one file. That's okay, but if the architecture is meant to be demonstrated with multiple carriers or failure modes, a few more demos (e.g., demo_seed_corruption.py, demo_model_mismatch.py) could illustrate the robustness of the gate.
· Tests location: tests/ is flat. For now, with few files, it's acceptable. If the number of tests grows, mirror the source tree.
· No CI mentioned: Adding a GitHub Action to run the single test suite would be low-effort and prevent regressions.

---

5. Repository Topics Suggestion

Add these GitHub topics:
seed-expansion, deterministic, physics-compression, protocol-design, zero-trust, pluggable-architecture, python-stdlib, orbital-mechanics, geomagnetic

End of review.
