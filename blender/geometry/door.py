"""Door generator (README section 11).

Like :mod:`blender.geometry.window`, the hole is already cut by the wall
generator. Here we add a jamb (three sides - no sill, doors meet the floor)
and the leaf itself, slightly inset so it reads as a door and not a plug.
"""

from __future__ import annotations

from typing import List, Optional

import bpy
from mathutils import Vector

from ..materials import palette
from . import common

JAMB_W = 0.09
JAMB_D = 0.06
LEAF_T = 0.06


def build_door(
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

    jambs = (
        ("top", (w, t + JAMB_D, JAMB_W), (0.0, 0.0, h / 2.0 - JAMB_W / 2.0)),
        ("left", (JAMB_W, t + JAMB_D, h), (-w / 2.0 + JAMB_W / 2.0, 0.0, 0.0)),
        ("right", (JAMB_W, t + JAMB_D, h), (w / 2.0 - JAMB_W / 2.0, 0.0, 0.0)),
    )
    for label, size, offset in jambs:
        obj = common.make_box(
            f"AIG_door_{wall.id}_{label}",
            size,
            Vector(centre) + Vector(offset),
            coll,
        )
        obj.matrix_world = matrix @ obj.matrix_world
        palette.assign(obj, "FRAME")
        common.shade_flat(obj)
        obj["aig_type"] = "door_frame"
        obj["aig_wall_id"] = wall.id
        objects.append(obj)

    leaf = common.make_box(
        f"AIG_door_{wall.id}_leaf",
        (w - 2 * JAMB_W, LEAF_T, h - JAMB_W),
        Vector(centre) + Vector((0.0, 0.0, -JAMB_W / 2.0)),
        coll,
    )
    leaf.matrix_world = matrix @ leaf.matrix_world
    palette.assign(leaf, "WOOD")
    common.shade_flat(leaf)
    leaf["aig_type"] = "door_leaf"
    leaf["aig_wall_id"] = wall.id
    objects.append(leaf)

    return objects
