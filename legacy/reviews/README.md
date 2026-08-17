# legacy/reviews/

Audits as they were written. **Not edited afterwards to match what we
later learned** — a review that has been tidied up in hindsight is no
longer evidence of anything.

Corrections live in [`../../NOTEBOOK.md`](../../NOTEBOOK.md), next to
the original claim, where the correction is legible as a correction.

| File | Commit | Written | Scope |
|---|---|---|---|
| `01-docs-review.md` | `eba4c42` | **before any code existed** | reviewed `CLAUDE.md` alone |
| `02-code-audit.md` | `8db1b05` | after the codebase landed | 12 findings against the actual source |

Both were previously loose in the repo root — `02` as `REVIEW.md`, `01`
appended to the bottom of `CLAUDE.md`, where it had been sitting since
before the code it speculated about was written.

## What the sequence is worth knowing for

The two reviews were written under different conditions, and the
difference in what they caught is the useful part.

**`01` was written blind** — CLAUDE.md existed, the code did not. So it
asks questions instead of making findings: *"Is the CRC correctly
computed? Does the Expander use `abc.ABC`? Verify no third-party
imports."* Round 2 finally ran all of them. **Every one held** (F-14):
the CRC gives the right check value, the ABC genuinely refuses
instantiation, there are no third-party imports.

That is a decent hit rate for guesswork, and it is also the limit of
it. The bugs that were actually there — `("ab","c")` colliding with
`("a","bc")` in two separate files, 80% of the seed entropy going
unread, `steps` silently changing the schedule's shape — are not on
`01`'s list. Not because it was careless, but because **none of them
are visible from the documentation.** They are visible from running the
code, which is what `02` did.

The lesson carried into `NOTEBOOK.md` as method step 2: *run it, do not
read it.* Review by inspection finds the things you already thought to
worry about. That is a real contribution, and it is not the same job as
finding what is actually broken.

Where `01` was strongest was where inspection genuinely is enough:
missing README, missing CITATION.cff, missing CI, no LICENSE reference,
no template for new expanders. Those were all correct, all still open a
round later, and all closed in round 2.
