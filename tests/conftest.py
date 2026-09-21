"""Let ``python3 -m pytest tests/`` work without Blender.

``test_geometry.py`` imports ``bpy`` at module level and is meant to be run by
``tests/run_in_blender.py``. Outside Blender that import fails and pytest
reports a collection ERROR, which looks like a broken test suite. Skip the
module instead.
"""

import pytest

collect_ignore = []

try:  # pragma: no cover - trivial
    import bpy  # noqa: F401
except ImportError:
    collect_ignore.append("test_geometry.py")
