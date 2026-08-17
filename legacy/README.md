# legacy/

**Nothing here is dead. Precedent carries.**

This repo sells one property:

> same seed + same model + same epoch = identical output.

"Forever" is part of that sentence. A seed minted under an old mode has
to keep expanding the same way after the mode is superseded, or the
contract was never real. So retired behaviour is quarantined here, not
removed.

## What is in here

| Path | What it is |
|---|---|
| `modes.py` | Definition site for every retired mode identifier, plus a `RETIRED` registry recording the original claim, the test that falsified it, and its replacement. |
| `reviews/round1-review.md` | The round-1 audit exactly as written. Not edited to match what we later learned — that would destroy the evidence. |

## The rules for this folder

1. **Retire, don't delete.** A mode leaves the defaults; it does not
   leave the codebase.
2. **One definition site.** Retired identifiers are defined here and
   imported by the module that still honours them. `grep -rn
   "legacy.modes" .` shows the entire legacy surface.
3. **Every retirement names its killer.** A `RETIRED` entry must cite a
   test that still exists and still passes. `tests/test_legacy.py`
   enforces this — the ledger cannot rot silently.
4. **Golden vectors are frozen.** `tests/test_legacy.py` pins the actual
   bytes each legacy mode produces. A refactor that changes them fails
   CI, whether or not anyone remembered the old mode existed.
5. **Reviews are append-only.** Corrections go in `NOTEBOOK.md` as a new
   round, with the old claim left standing next to what replaced it.

## Reading a retirement

```python
from legacy.modes import explain
print(explain("KEY_V1"))
```

```
KEY_V1 = 1   [F-03]
  honoured by  : expanders.geomagnetic.FieldModel(key_version=...)
  use instead  : expanders.geomagnetic.KEY_V2
  claim made   : anchor + lattice_hash is a unique key per place.
  falsified by : tests/test_stack.py::test_key_v1_collision
  what the run showed:
    Falsified. ('abc', '') and ('ab', 'c') derive the same HMAC key. ...
```

Or dump all of them:

```
PYTHONPATH=. python -m legacy.modes
```
