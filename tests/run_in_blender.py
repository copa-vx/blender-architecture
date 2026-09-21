#!/usr/bin/env python3
"""Minimal test runner for the tests that need Blender.

    blender --background --python tests/run_in_blender.py

Blender's bundled Python has no pytest, so this collects ``test_*`` functions
from ``tests/test_geometry.py`` and runs them, printing a pytest-ish report.
Exits non-zero on failure so CI can use it.
"""

from __future__ import annotations

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for path in (REPO, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    import test_geometry

    tests = [
        (name, getattr(test_geometry, name))
        for name in sorted(dir(test_geometry))
        if name.startswith("test_") and callable(getattr(test_geometry, name))
    ]

    print(f"\n{'=' * 70}")
    print(f"running {len(tests)} geometry test(s) in Blender {os.environ.get('BLENDER_VERSION', '')}")
    import bpy

    print(f"Blender {bpy.app.version_string}, Python {sys.version.split()[0]}")
    print("=" * 70)

    passed, failed = [], []
    started = time.time()

    for name, func in tests:
        try:
            func()
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc, traceback.format_exc()))
            print(f"FAIL  {name}")
        else:
            passed.append(name)
            print(f"ok    {name}")

    elapsed = time.time() - started
    print("-" * 70)
    for name, exc, tb in failed:
        print(f"\nFAILURE: {name}\n{tb}")

    print("=" * 70)
    status = "PASSED" if not failed else "FAILED"
    print(f"{len(passed)} passed, {len(failed)} failed in {elapsed:.2f}s  [{status}]")
    print("=" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    # sys.exit inside Blender's --python is respected as the process exit code.
    sys.exit(code)
