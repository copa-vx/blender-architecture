"""Window generator (README section 11).

The hole itself is cut by :mod:`blender.geometry.wall`; this module only fills
it with a frame and a glass pane. Both are built in the wall's LOCAL frame and
then transformed, so the window is positioned from the wall's current length -
resize the wall and the window slides with it.
"""

from __future__ import annotations

from typing import List, Optional

import bpy
from mathutils import Vector

from ..materials import palette
from . import common

FRAME_W = 0.08   # how far the frame reaches into the opening
FRAME_D = 0.06   # frame depth beyond the wall face
GLASS_T = 0.02


def build_window(
    wall,
    opening,
    coll: Optional["bpy.types.Collection"] = None,
) -> List["bpy.types.Object"]:
    coll = coll or common.get_subcollection("Openings")
    matrix = common.wall_matrix(wall)
    centre = common.opening_local_centre(wall, opening)
    w = float(opening.width)
    h = float(opening.height)
    t = float(wall.thickness)

    objects: List["bpy.types.Object"] = []

    # --- frame: four bars around the opening ------------------------------
    bars = (
        # (name, size, local offset from the opening centre)
        ("bottom", (w, t + FRAME_D, FRAME_W), (0.0, 0.0, -h / 2.0 + FRAME_W / 2.0)),
        ("top", (w, t + FRAME_D, FRAME_W), (0.0, 0.0, h / 2.0 - FRAME_W / 2.0)),
        ("left", (FRAME_W, t + FRAME_D, h), (-w / 2.0 + FRAME_W / 2.0, 0.0, 0.0)),
        ("right", (FRAME_W, t + FRAME_D, h), (w / 2.0 - FRAME_W / 2.0, 0.0, 0.0)),
    )
    for label, size, offset in bars:
        obj = common.make_box(
            f"AIG_window_{wall.id}_{label}",
            size,
            Vector(centre) + Vector(offset),
            coll,
        )
        obj.matrix_world = matrix @ obj.matrix_world
        palette.assign(obj, "FRAME")
        common.shade_flat(obj)
        obj["aig_type"] = "window_frame"
        obj["aig_wall_id"] = wall.id
        objects.append(obj)

    # --- glass -------------------------------------------------------------
    glass = common.make_box(
        f"AIG_window_{wall.id}_glass",
        (w - 2 * FRAME_W, GLASS_T, h - 2 * FRAME_W),
        centre,
        coll,
    )
    glass.matrix_world = matrix @ glass.matrix_world
    palette.assign(glass, "GLASS")
    common.shade_flat(glass)
    glass["aig_type"] = "window_glass"
    glass["aig_wall_id"] = wall.id
    objects.append(glass)

    return objects
