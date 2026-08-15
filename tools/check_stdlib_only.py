#!/usr/bin/env python3
"""
check_stdlib_only.py — enforce the house rule.

CLAUDE.md says: "stdlib only. No deps. Must run on a phone." That is a
hard constraint, and a hard constraint that nothing checks is a wish.
This walks every .py file in the repo, parses it (no importing — a
dependency must not be installed for the check to run), and fails if any
import resolves to something outside the standard library or this repo.

    python tools/check_stdlib_only.py

Exit 0 = clean. Exit 1 = a dependency got in.
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LOCAL = {"core", "expanders", "integration", "legacy", "tests", "tools"}


def stdlib_names() -> set:
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    # Python < 3.10 has no stdlib_module_names. Fall back to the set this
    # repo actually uses, so the check still means something there.
    return {
        "abc", "ast", "dataclasses", "hashlib", "hmac", "math", "pathlib",
        "struct", "sys", "typing", "unittest", "__future__",
    }


def top_level_imports(tree: ast.AST) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # relative import — always local
                continue
            if node.module:
                found.add(node.module.split(".")[0])
    return found


def main() -> int:
    allowed = stdlib_names() | LOCAL
    violations = []
    checked = 0

    for path in sorted(REPO.rglob("*.py")):
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        checked += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            violations.append(f"{path.relative_to(REPO)}: does not parse — {e}")
            continue
        for name in sorted(top_level_imports(tree)):
            if name not in allowed:
                violations.append(f"{path.relative_to(REPO)}: imports {name!r}")

    if violations:
        print("FAIL — stdlib-only rule broken:")
        for v in violations:
            print(f"  {v}")
        print("\nCLAUDE.md: 'stdlib only. No deps. Must run on a phone.'")
        return 1

    print(f"ok  stdlib-only: {checked} files, no third-party imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
