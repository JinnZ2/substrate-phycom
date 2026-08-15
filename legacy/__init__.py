"""
legacy — the parts that were superseded but not deleted.

Precedent carries. A result that has been falsified is still a result,
and a seed minted under an old mode still has to expand. Nothing in here
is dead code; it is the older dialect of a protocol that promises
determinism forever.

  modes.py   : retired mode identifiers + the evidence that retired them
  reviews/   : audits as they were written, unedited after the fact

Current defaults live in core/ and expanders/. See ../NOTEBOOK.md for the
full ledger of what was claimed, what was run, and what fell over.

    from legacy.modes import RETIRED, explain

Deliberately empty otherwise: importing legacy.modes here would make
`python -m legacy.modes` warn about double-import under runpy.
"""
