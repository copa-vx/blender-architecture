"""Ground plane sized to the house plus a margin (README section 14, minimal).

The plane is subdivided and *lightly* displaced with a deterministic value
noise so it is not perfectly flat, but the area under the house is flattened
back to z=0 so the building never floats or sinks. Full procedural terrain
is Milestone 2.
"""

from __future__ import annotations

import math
from typing import Optional

import bmesh
import bpy
from mathutils import Vector

from ..materials import palette
from ..geometry import common

#: How strong the bumps are, in metres.
AMPLITUDE = 0.18
#: Grid subdivisions per side.
RESOLUTION = 32


def _value_noise(x: float, y: float, seed: int) -> float:
    """Cheap deterministic pseudo-noise in [-1, 1] - no bpy/numpy dependency."""
    n = math.sin(x * 12.9898 + y * 78.233 + seed * 0.137) * 43758.5453
    return (n - math.floor(n)) * 2.0 - 1.0


def build_terrain(
    house,
    coll: Optional["bpy.types.Collection"] = None,
    material: str = "GRASS",
) -> "bpy.types.Object":
    coll = coll or common.get_subcollection("Environment")
    x0, y0, x1, y1 = house.footprint()
    margin = float(house.terrain_margin)
    size = max(x1 - x0, y1 - y0) + 2 * margin
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    bm = bmesh.new()
    bmesh.ops.create_grid(
        bm, x_segments=RESOLUTION, y_segments=RESOLUTION, size=size / 2.0
    )
    bmesh.ops.translate(bm, vec=Vector((cx, cy, 0.0)), verts=bm.verts)

    # displace, but keep the building pad flat
    pad_x = (x1 - x0) / 2.0 + 1.0
    pad_y = (y1 - y0) / 2.0 + 1.0
    for vert in bm.verts:
        dx = abs(vert.co.x - cx)
        dy = abs(vert.co.y - cy)
        if dx <= pad_x and dy <= pad_y:
            continue
        # fade the displacement in over 2 m so there is no cliff at the pad
        fade = min(1.0, max(dx - pad_x, dy - pad_y) / 2.0)
        vert.co.z = _value_noise(vert.co.x, vert.co.y, house.seed) * AMPLITUDE * fade

    obj = common.new_mesh_object("AIG_terrain", bm, coll)
    palette.assign(obj, material)
    common.shade_flat(obj)
    obj["aig_type"] = "terrain"
    obj["aig_size"] = size
    return obj
