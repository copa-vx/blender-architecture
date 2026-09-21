"""AI GLADE Blender addon.

Registers a small property group on the Scene, an N-panel in the 3D viewport
and four operators (Generate / Load JSON / Save JSON / Clear).

Supports both addon systems:
* ``bl_info`` for the classic addon loader (<= 4.1 and still accepted later);
* ``blender_manifest.toml`` next to this file for the 4.2+ extension system.

The addon is a thin shell: all it does is turn panel values into a
:class:`blender.model.House` and hand it to the generator. No geometry logic
lives here.
"""

from __future__ import annotations

import os
import sys

bl_info = {
    "name": "AI GLADE - Procedural House",
    "author": "ai-glade contributors",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > AI GLADE",
    "description": "Parametric procedural house builder (Milestone 1)",
    "category": "Add Mesh",
}

# The addon may be loaded from an install directory that is not on sys.path;
# make the repo root importable so `blender.model` resolves.
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from . import operators, panels, properties  # noqa: E402

_MODULES = (properties, operators, panels)


def register() -> None:
    for module in _MODULES:
        module.register()


def unregister() -> None:
    for module in reversed(_MODULES):
        module.unregister()


if __name__ == "__main__":
    register()
