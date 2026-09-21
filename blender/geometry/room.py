"""Room generator (README section 10).

A room contributes its floor slab here; its *walls* are produced by
:mod:`blender.geometry.wall` from the derived wall list, because a wall
between two rooms belongs to both of them and must only be built once.
"""

from __future__ import annotations

from typing import List, Optional

import bpy

from ..materials import palette
from . import common

#: Thickness of the floor slab, drawn below floor level.
SLAB = 0.12


def build_room_floor(
    room,
    base_z: float = 0.0,
    coll: Optional["bpy.types.Collection"] = None,
    material: str = "WOOD",
) -> "bpy.types.Object":
    """One flat slab per room, sitting just under ``base_z``."""
    coll = coll or common.get_subcollection("Floors")
    cx, cy = room.centre
    obj = common.make_box(
        f"AIG_floor_{room.name}",
        (float(room.width), float(room.depth), SLAB),
        (cx, cy, base_z - SLAB / 2.0),
        coll,
    )
    palette.assign(obj, material)
    common.shade_flat(obj)
    obj["aig_type"] = "floor"
    obj["aig_room"] = room.name
    obj["aig_area"] = room.area
    return obj


def build_floor_slabs(
    floor,
    base_z: float = 0.0,
    coll: Optional["bpy.types.Collection"] = None,
    material: str = "WOOD",
) -> List["bpy.types.Object"]:
    coll = coll or common.get_subcollection("Floors")
    return [
        build_room_floor(room, base_z=base_z, coll=coll, material=material)
        for room in floor.rooms
    ]
